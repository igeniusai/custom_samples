"""hermes-platform-gateway plugin — gateway-mode multi-conversation adapter.

Registers a Domyn platform adapter via ``ctx.register_platform``. The
adapter opens one WebSocket per worker to the Domyn relay and routes
each ``conversation_id`` to its own hermes session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

from .client import (
    RefreshLoop,
    build_ws_url,
    fetch_tools,
)
from .schema import convert_schema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED = ("DOMYN_API_KEY", "DOMYN_BASE_URL", "DOMYN_SPACE_ID", "DOMYN_CHANNEL_ID")


# ---------------------------------------------------------------------------
# Helpers — pure functions, no adapter / hermes state
# ---------------------------------------------------------------------------


def _extract_last_reasoning(conversation_history: Any) -> str:
    """Return the current turn's reasoning trace, or ``""`` when absent.

    Walks ``conversation_history`` backwards and picks the last assistant
    message whose ``reasoning`` field is populated, stopping at the user
    message that started the turn. Mirrors hermes' own extraction at
    ``run_agent.py:14066-14072``.
    """
    if not conversation_history:
        return ""
    for msg in reversed(list(conversation_history)):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            break
        if msg.get("role") != "assistant":
            continue
        reasoning = msg.get("reasoning") or msg.get("reasoning_content")
        if not reasoning:
            continue
        if isinstance(reasoning, str):
            return reasoning
        if isinstance(reasoning, list):
            parts: list[str] = []
            for item in reasoning:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("thinking") or ""
                    if text:
                        parts.append(str(text))
            if parts:
                return "\n".join(parts)
    return ""


# TODO(thought-process): drop the hardcoded placeholder once the active
# provider surfaces ``reasoning_content`` on assistant messages.
def _hardcoded_tool_thought(tool_name: str, args: Any) -> str:
    """Placeholder ``ToolAction.thought`` text when no real reasoning is available."""
    try:
        args_preview = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())[:200]
    except Exception:
        args_preview = ""
    suffix = f" with {args_preview}" if args_preview else ""
    return (
        f"[hardcoded placeholder] Hermes is invoking `{tool_name}`{suffix}. "
        "Real reasoning will appear here once the LLM provider exposes "
        "reasoning_content."
    )


# ---------------------------------------------------------------------------
# Hermes runtime lookups — read-only access to gateway internals
# ---------------------------------------------------------------------------


def _runner_ref_or_none() -> Any:
    """Return the live ``GatewayRunner`` instance, or None."""
    try:
        from gateway.run import _gateway_runner_ref
    except Exception:
        return None
    return _gateway_runner_ref() if _gateway_runner_ref else None


def _chat_id_and_thought_for_task(task_id: str) -> tuple[str | None, str]:
    """Return ``(chat_id, current_thought)`` for the AIAgent driving *task_id*.

    Scans the gateway's ``_running_agents`` for the agent whose
    ``_current_task_id`` matches, then pulls both its ``_chat_id`` and the
    most-recent reasoning trace within the current turn so the platform
    can render *why* hermes is invoking each tool, not just *that* it is.
    Returns ``(None, "")`` when the lookup fails.
    """
    runner = _runner_ref_or_none()
    if runner is None:
        return None, ""
    running = getattr(runner, "_running_agents", None) or {}
    for agent in running.values():
        if getattr(agent, "_current_task_id", None) != task_id:
            continue
        chat_id = getattr(agent, "_chat_id", None)
        thought = _extract_last_reasoning(getattr(agent, "messages", None))
        return chat_id, thought
    return None, ""


# ---------------------------------------------------------------------------
# Async dispatch — hooks fire on hermes' worker thread; outbound sends
# must reach the relay client's loop or websockets raises about loop
# affinity. ``_schedule_on_gateway_loop`` is the cross-loop bridge.
# ---------------------------------------------------------------------------


def _schedule_on_gateway_loop(coro: Any, *, label: str) -> None:
    """Fire-and-forget schedule of *coro* on the gateway's event loop."""
    runner = _runner_ref_or_none()
    gateway_loop = getattr(runner, "_gateway_loop", None) if runner else None
    if gateway_loop is not None and not gateway_loop.is_closed():
        try:
            asyncio.run_coroutine_threadsafe(coro, gateway_loop)
            return
        except Exception as exc:
            logger.warning("platform-gateway: schedule %s failed - %s", label, exc)
    # Same-loop fallback for tests / synchronous contexts.
    try:
        asyncio.get_event_loop().create_task(coro)
    except Exception as exc:
        logger.warning("platform-gateway: fallback %s dispatch failed - %s", label, exc)


# ---------------------------------------------------------------------------
# Refresh loop and tool handler factory — module-level so tests can stub
# the daemon thread and so ``RefreshLoop._refresh`` can rebuild handlers
# when new canvas tools appear.
# ---------------------------------------------------------------------------


def _start_refresh_loop(**kwargs: Any) -> None:
    """Indirection so tests can stub the daemon thread."""
    RefreshLoop(**kwargs).start()


def _make_tool_handler(
    adapter_slot: list[Any], tool_name: str, timeout: float
) -> Callable[..., Any]:
    """Build the async handler that bridges hermes' tool registry to the adapter.

    The registry only passes ``task_id`` to platform tool handlers (not
    ``parent_agent``), so we look up the chat_id via the per-task stash
    that ``pre_tool_call`` populated.
    """

    async def handler(args: dict, **kwargs: Any) -> str:
        adapter = adapter_slot[0]
        if adapter is None:
            return json.dumps({"error": "platform-gateway: adapter not ready"})
        task_id = kwargs.get("task_id") or ""
        chat_id = adapter._chat_id_by_task.get(task_id)
        if not chat_id:
            return json.dumps({"error": "platform-gateway: no chat_id for task_id"})
        session_key = adapter.session_key_for_chat(chat_id)
        thought = adapter.thought_for_task(task_id)
        return await adapter.call_tool(
            session_key=session_key,
            tool_name=tool_name,
            args=args,
            thought=thought,
            timeout=timeout,
        )

    return handler


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def register(ctx: Any) -> None:
    """Plugin entry — called once by hermes' plugin loader at startup."""
    missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if missing:
        logger.warning(
            "platform-gateway: skipping registration — missing env vars: %s",
            ", ".join(missing),
        )
        return

    api_key = os.environ["DOMYN_API_KEY"]
    base_url = os.environ["DOMYN_BASE_URL"].rstrip("/")
    space_id = os.environ["DOMYN_SPACE_ID"]
    channel_id = os.environ["DOMYN_CHANNEL_ID"]
    configuration_id = os.environ.get("DOMYN_CONFIGURATION_ID") or None
    timeout = float(os.environ.get("PLATFORM_TOOL_TIMEOUT", "120"))
    refresh_interval = float(os.environ.get("PLATFORM_TOOL_REFRESH_INTERVAL", "60"))

    try:
        raw_tools = fetch_tools(
            base_url,
            space_id,
            channel_id,
            api_key,
            configuration_id=configuration_id,
        )
    except Exception as exc:
        logger.warning("platform-gateway: could not fetch tools - %s", exc)
        raw_tools = []

    # Adapter is built lazily by the factory so the gateway controls
    # its lifecycle. We close over a one-slot list so the tool
    # handlers (registered now) can find the live adapter once the
    # factory has been called.
    adapter_slot: list[Any] = [None]
    ws_url = build_ws_url(base_url)
    headers = {"channel-id": channel_id, "space-id": space_id, "api-key": api_key}

    def _factory(config: Any) -> Any:
        from .adapter import DomynPlatformAdapter
        from .relay_client import DomynRelayClient

        def relay_factory(on_event: Callable[[Any], Any]) -> Any:
            return DomynRelayClient(ws_url=ws_url, headers=headers, on_event=on_event)

        adapter = DomynPlatformAdapter(
            config=config,
            channel_id=channel_id,
            relay_client_factory=relay_factory,
        )
        adapter_slot[0] = adapter
        return adapter

    def _check() -> bool:
        return all(os.environ.get(v) for v in _REQUIRED)

    ctx.register_platform(
        name="domyn",
        label="Domyn",
        adapter_factory=_factory,
        check_fn=_check,
        required_env=list(_REQUIRED),
        allowed_users_env="DOMYN_ALLOWED_USERS",
        allow_all_env="DOMYN_ALLOW_ALL_USERS",
    )

    # --- Tool registration ---
    registered_names: set[str] = set()
    for tool_def in raw_tools:
        name = tool_def.get("name")
        if not name:
            continue
        try:
            schema = convert_schema(tool_def)
        except Exception as exc:
            logger.warning("platform-gateway: skipping tool '%s' - schema error: %s", name, exc)
            continue
        ctx.register_tool(
            name=name,
            toolset="platform",
            schema=schema,
            handler=_make_tool_handler(adapter_slot, name, timeout),
            is_async=True,
        )
        registered_names.add(name)
    logger.info(
        "platform-gateway: registered domyn adapter with %d platform tool(s): %s",
        len(registered_names),
        sorted(registered_names),
    )

    # --- Hooks ---
    # pre_tool_call bridges the AIAgent → tool-handler gap: hermes' tool
    # registry only passes ``task_id`` to the handler (not ``parent_agent``),
    # so we scan _running_agents for the matching agent and stash its
    # chat_id (+ current reasoning) under task_id. post_tool_call drops
    # the stash and emits a visibility TOOL_END for built-in tools.
    _platform_tool_names: set[str] = set(registered_names)

    def _on_pre_tool_call(
        tool_name: str = "",
        args: Any = None,
        task_id: str = "",
        **_: Any,
    ) -> None:
        adapter = adapter_slot[0]
        if adapter is None or not task_id:
            return
        chat_id, thought = _chat_id_and_thought_for_task(task_id)
        if not chat_id:
            return

        is_platform = tool_name in _platform_tool_names
        effective_thought = thought or _hardcoded_tool_thought(tool_name, args)
        logger.debug(
            "platform-gateway: pre_tool_call %s task_id=%s chat_id=%s is_platform=%s has_real_thought=%s",
            tool_name,
            task_id,
            chat_id,
            is_platform,
            bool(thought),
        )

        # Always stash chat_id (+ thought) — post_tool_call reads this
        # back regardless of branch.
        adapter.record_task_chat(
            task_id=task_id,
            chat_id=chat_id,
            thought=effective_thought,
        )

        if is_platform:
            # Real platform tool: the canonical TOOL_START goes out
            # from adapter.call_tool with a pending future. Done here.
            return

        # Built-in hermes tool: visibility-only TOOL_START. Generate a
        # fresh call_id, stash it so post_tool_call can pair the TOOL_END.
        call_id = f"visibility-{uuid.uuid4()}"
        adapter.record_visibility_call(task_id=task_id, call_id=call_id)
        _schedule_on_gateway_loop(
            adapter.emit_visibility_tool_start(
                chat_id=chat_id,
                tool_name=tool_name,
                args=args if isinstance(args, dict) else {},
                thought=effective_thought,
                call_id=call_id,
            ),
            label=f"visibility TOOL_START {tool_name}",
        )

    def _on_post_tool_call(
        tool_name: str = "",
        task_id: str = "",
        result: Any = None,
        **_: Any,
    ) -> None:
        adapter = adapter_slot[0]
        if adapter is None:
            return
        chat_id = adapter._chat_id_by_task.get(task_id)
        visibility_call_id = adapter.pop_visibility_call(task_id)
        adapter.forget_task(task_id=task_id)

        # Visibility TOOL_END only for built-in tools that emitted a
        # matching visibility TOOL_START. Platform tools have their own
        # TOOL_END round-trip from the relay; don't double-emit.
        if not visibility_call_id or tool_name in _platform_tool_names:
            return
        if not chat_id:
            return
        _schedule_on_gateway_loop(
            adapter.emit_visibility_tool_end(
                chat_id=chat_id,
                tool_name=tool_name,
                call_id=visibility_call_id,
                observation=result,
            ),
            label=f"visibility TOOL_END {tool_name}",
        )

    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    # END is emitted by the adapter's on_processing_complete override —
    # see ``DomynPlatformAdapter.on_processing_complete`` for the
    # rationale (post_llm_call/on_session_end both fire too early).

    # --- Tool list refresh ---
    if refresh_interval > 0:
        _start_refresh_loop(
            ctx=ctx,
            handler_factory=lambda nm: _make_tool_handler(adapter_slot, nm, timeout),
            base_url=base_url,
            space_id=space_id,
            channel_id=channel_id,
            api_key=api_key,
            interval=refresh_interval,
            initial_names=registered_names,
            configuration_id=configuration_id,
        )
