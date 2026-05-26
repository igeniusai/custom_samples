"""Platform relay client: tool discovery and WebSocket connection management."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import random
import threading
import time
import uuid
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

_LOCALHOST = ("localhost", "127.0.0.1", "::1")


def _is_localhost(base_url: str) -> bool:
    host = base_url.split("/")[0].split(":")[0]
    return host in _LOCALHOST or base_url.startswith("localhost:")


def build_ws_url(base_url: str) -> str:
    """Return ws:// for localhost, wss:// otherwise.

    Mirrors ``domyn expose._build_ws_url`` — strips any ``http://``/``https://``
    prefix (the env var sometimes carries one) and uses the raw hostname (no
    ``api.`` prefix), unlike the HTTP API URL.
    """
    for prefix in ("https://", "http://"):
        if base_url.startswith(prefix):
            base_url = base_url[len(prefix):]
            break
    base_url = base_url.rstrip("/")
    scheme = "ws" if _is_localhost(base_url) else "wss"
    return f"{scheme}://{base_url}/relay/v1/ws"


def build_api_base_url(base_url: str) -> str:
    """Translate ``<host>`` into ``https://api.<host>``.

    Mirrors ``domyn expose._build_api_base`` / ``domyn_platform._resolve_platform_args``
    — every platform HTTP call goes through the ``api.`` subdomain. Localhost
    is special-cased so the in-process stub keeps working unchanged.
    """
    if _is_localhost(base_url):
        return f"http://{base_url.rstrip('/')}"
    transformed = base_url.replace("://", "://api.")
    if not transformed.startswith(("http://", "https://")):
        transformed = f"https://api.{transformed}"
    return transformed.rstrip("/")


def fetch_tools(
    base_url: str,
    space_id: str,
    channel_id: str,
    api_key: str,
    configuration_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch the canvas tool list from the platform (synchronous HTTP POST).

    Matches ``domyn_agents.integrations.langgraph.domyn_platform._fetch_tool_definitions``:
    endpoint is ``list_delegate_tools_for_channel`` and the body carries
    ``space_id``, ``channel_id`` and optional ``configuration_id``.
    """
    api_base = build_api_base_url(base_url)
    url = f"{api_base}/api/agents-service/tool/list_delegate_tools_for_channel"
    resp = httpx.post(
        url,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "space_id": space_id,
            "channel_id": channel_id,
            "configuration_id": configuration_id,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tools", "data", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
    raise ValueError(f"Unexpected tool list response shape: {type(data)}")


class GatewayConnection:
    """Manages a persistent WebSocket to the platform relay.

    Spawns a daemon thread on start() that owns a single asyncio event loop.
    That loop maintains the WebSocket connection with full-jitter exponential
    backoff reconnection and a receive loop that resolves pending
    concurrent.futures.Future objects when TOOL_END / TOOL_ERROR arrives.

    Tool handlers call call_tool() synchronously — it blocks on future.result()
    until the platform responds.
    """

    def __init__(
        self,
        ws_url: str,
        headers: dict[str, str],
        timeout: float = 120.0,
        on_agent_start: Callable[["BaseEvent"], None] | None = None,
        on_stop: Callable[[], None] | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._headers = headers
        self._timeout = timeout
        self._on_agent_start = on_agent_start
        self._on_stop = on_stop
        self._pending: dict[str, concurrent.futures.Future] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: Any = None
        self._ready = threading.Event()
        self._stop_requested = threading.Event()

    def start(self) -> None:
        """Spawn the background WebSocket thread and wait up to 15s for first connect."""
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        if not self._ready.wait(timeout=15):
            logger.warning("platform-gateway: timed out waiting for initial WebSocket connection")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self) -> None:
        import websockets

        attempt = 0
        while True:
            try:
                async with websockets.connect(
                    self._ws_url, additional_headers=self._headers
                ) as ws:
                    self._ws = ws
                    self._ready.set()
                    attempt = 0
                    await self._receive_loop(ws)
                    code = getattr(ws, "close_code", None)
                    reason = (
                        getattr(ws, "close_reason", None)
                        or getattr(ws, "close_message", None)
                    )
                    logger.info(
                        "platform-gateway: WebSocket closed by server (code=%s, reason=%r)",
                        code, reason,
                    )
            except Exception as exc:
                logger.warning("platform-gateway: WebSocket error - %s", exc)
                self._fail_pending("WebSocket disconnected")
                self._ws = None

            delay = min(30.0, 0.5 * (2 ** attempt)) * (0.5 + 0.5 * random.random())
            logger.debug("platform-gateway: reconnecting in %.1fs", delay)
            await asyncio.sleep(delay)
            attempt = min(attempt + 1, 6)

    async def _receive_loop(self, ws: Any) -> None:
        from domyn_agents.core import ExecutionEventType, RelayMessage

        async for raw in ws:
            try:
                msg = RelayMessage.model_validate_json(raw)
                event = msg.payload
            except Exception:
                continue

            if event.event_type == ExecutionEventType.AGENT_START:
                self._stop_requested.clear()
                if self._on_agent_start is not None:
                    try:
                        self._on_agent_start(event)
                    except Exception as exc:
                        logger.warning("platform-gateway: on_agent_start callback failed - %s", exc)
                continue

            if event.event_type == ExecutionEventType.AGENT_END:
                # An AGENT_END arriving from the platform (not echoed from Hermes itself,
                # since the relay excludes the sender) is a cancellation signal.
                logger.info("platform-gateway: received AGENT_END from platform — stopping current turn")
                self._stop_requested.set()
                self._fail_pending("Execution cancelled by user")
                if self._on_stop is not None:
                    try:
                        self._on_stop()
                    except Exception as exc:
                        logger.warning("platform-gateway: on_stop callback failed - %s", exc)
                continue

            if event.event_type not in (
                ExecutionEventType.TOOL_END,
                ExecutionEventType.TOOL_ERROR,
            ):
                continue

            call_id = getattr(event.action, "call_id", None) if event.action else None
            if not call_id:
                continue

            with self._lock:
                future = self._pending.pop(call_id, None)

            if future is None or future.done():
                continue

            if event.event_type == ExecutionEventType.TOOL_ERROR:
                future.set_exception(
                    RuntimeError(
                        event.error_message or f"platform tool error ({event.error_code})"
                    )
                )
            else:
                observation = (
                    getattr(event.action, "observation", None) if event.action else None
                )
                future.set_result(observation)

    def send_event(self, event: "BaseEvent") -> None:
        """Send a relay event back to the platform (fire-and-forget)."""
        if self._ws is None or self._loop is None:
            return
        from domyn_agents.core import RelayMessage
        msg = RelayMessage(payload=event).model_dump_json()
        try:
            asyncio.run_coroutine_threadsafe(self._ws.send(msg), self._loop)
        except Exception as exc:
            logger.debug("platform-gateway: send_event failed - %s", exc)

    def _fail_pending(self, reason: str) -> None:
        with self._lock:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(RuntimeError(reason))
            self._pending.clear()

    def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        turn: Any = None,
        **kwargs: Any,
    ) -> str:
        """Send TOOL_START and block until TOOL_END/TOOL_ERROR or timeout.

        ``turn`` is the originating AGENT_START :class:`BaseEvent`. When provided
        we copy ``author``/``interaction_id``/``turn_id``/``conversation_id`` onto
        the TOOL_START so the platform can route the call to the right session —
        this mirrors ``Runtime.call_platform_tool`` in ``domyn-agents``.

        Always returns a JSON string. Never raises.
        """
        from domyn_agents.core import BaseEvent, ExecutionEventType, RelayMessage, ToolAction

        if self._ws is None or self._loop is None:
            return json.dumps({"error": "platform-gateway: WebSocket not connected"})

        call_id = str(uuid.uuid4())
        future: concurrent.futures.Future = concurrent.futures.Future()
        with self._lock:
            self._pending[call_id] = future

        event = RelayMessage(
            payload=BaseEvent(
                event_type=ExecutionEventType.TOOL_START,
                author=getattr(turn, "author", None) or "hermes",
                interaction_id=getattr(turn, "interaction_id", None),
                turn_id=getattr(turn, "turn_id", None),
                conversation_id=getattr(turn, "conversation_id", None),
                action=ToolAction(name=tool_name, parameters=args, call_id=call_id),
            )
        )

        try:
            send_fut = asyncio.run_coroutine_threadsafe(
                self._ws.send(event.model_dump_json()),
                self._loop,
            )
            send_fut.result(timeout=10)
        except Exception as exc:
            with self._lock:
                self._pending.pop(call_id, None)
            return json.dumps({"error": f"platform-gateway: send failed - {exc}"})

        try:
            observation = future.result(timeout=self._timeout)
            return _serialize_observation(observation)
        except concurrent.futures.TimeoutError:
            with self._lock:
                self._pending.pop(call_id, None)
            return json.dumps({"error": f"Tool '{tool_name}' timed out after {self._timeout}s"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})


def _serialize_observation(observation: Any) -> str:
    """Serialize a platform tool observation to a JSON string.

    If observation is already a valid JSON string, return it as-is.
    Otherwise wrap in {"result": observation}.
    """
    if isinstance(observation, str):
        try:
            json.loads(observation)
            return observation
        except json.JSONDecodeError:
            pass
    return json.dumps({"result": observation})


def _deregister_tool(name: str) -> None:
    """Remove a tool from the hermes tool registry."""
    try:
        from tools.registry import registry
        registry.deregister(name)
        logger.info("platform-gateway: deregistered tool '%s'", name)
    except ImportError:
        logger.debug("platform-gateway: tools.registry unavailable, cannot deregister '%s'", name)


class RefreshLoop:
    """Periodically re-fetches the canvas tool list and syncs the hermes registry.

    Runs in a daemon thread. On each interval it diffs the live tool list against
    the currently-registered set: new tools are registered, removed tools are
    deregistered. Unchanged tools are left alone.

    Pass ``_deregister`` in tests to avoid the hermes registry import.
    """

    def __init__(
        self,
        ctx: Any,
        handler_factory: Callable[[str], Callable],
        base_url: str,
        space_id: str,
        channel_id: str,
        api_key: str,
        interval: float,
        initial_names: set[str],
        configuration_id: str | None = None,
        _deregister: Callable[[str], None] | None = None,
    ) -> None:
        self._ctx = ctx
        self._handler_factory = handler_factory
        self._base_url = base_url
        self._space_id = space_id
        self._channel_id = channel_id
        self._configuration_id = configuration_id
        self._api_key = api_key
        self._interval = interval
        self._registered: set[str] = set(initial_names)
        self._deregister_fn = _deregister if _deregister is not None else _deregister_tool

    def start(self) -> None:
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self) -> None:
        while True:
            time.sleep(self._interval)
            self._refresh()

    def _refresh(self) -> None:
        from hermes_platform_gateway.schema import convert_schema

        try:
            raw_tools = fetch_tools(
                self._base_url,
                self._space_id,
                self._channel_id,
                self._api_key,
                configuration_id=self._configuration_id,
            )
        except Exception as exc:
            logger.warning("platform-gateway: refresh fetch failed - %s", exc)
            return

        new_defs = {t["name"]: t for t in raw_tools if t.get("name")}
        new_names = set(new_defs.keys())

        added = new_names - self._registered
        removed = self._registered - new_names

        if not added and not removed:
            return

        for name in removed:
            self._deregister_fn(name)

        for name in added:
            try:
                schema = convert_schema(new_defs[name])
            except Exception as exc:
                logger.warning("platform-gateway: skipping new tool '%s': %s", name, exc)
                continue
            self._ctx.register_tool(
                name=name,
                toolset="platform",
                schema=schema,
                handler=self._handler_factory(name),
                is_async=False,
            )

        logger.info(
            "platform-gateway: canvas refresh - +%d added, -%d removed",
            len(added),
            len(removed),
        )
        self._registered = new_names
