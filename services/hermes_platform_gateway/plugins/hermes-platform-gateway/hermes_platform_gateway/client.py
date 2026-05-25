"""Platform relay client: tool discovery and WebSocket connection management."""
from __future__ import annotations

import logging
import threading
import time
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
                is_async=True,
            )

        logger.info(
            "platform-gateway: canvas refresh - +%d added, -%d removed",
            len(added),
            len(removed),
        )
        self._registered = new_names
