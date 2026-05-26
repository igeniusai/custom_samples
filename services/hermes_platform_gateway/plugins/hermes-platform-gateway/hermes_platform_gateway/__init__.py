"""Hermes platform gateway plugin — registers canvas tools dynamically at startup."""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_REQUIRED = ("DOMYN_API_KEY", "DOMYN_BASE_URL", "DOMYN_SPACE_ID", "DOMYN_CHANNEL_ID")


def register(ctx) -> None:
    """Called once by the hermes plugin loader at startup.

    Fetches the current canvas tool list from the platform and registers
    each as a sync handler that forwards calls over the WebSocket relay.
    Also wires up bidirectional relay: AGENT_START injects user input into
    hermes, and on_stream_token / post_llm_call hooks stream the response back.
    """
    api_key = os.environ.get("DOMYN_API_KEY", "")
    base_url = os.environ.get("DOMYN_BASE_URL", "").rstrip("/")
    space_id = os.environ.get("DOMYN_SPACE_ID", "")
    channel_id = os.environ.get("DOMYN_CHANNEL_ID", "")
    configuration_id = os.environ.get("DOMYN_CONFIGURATION_ID") or None
    timeout = float(os.environ.get("PLATFORM_TOOL_TIMEOUT", "120"))
    refresh_interval = float(os.environ.get("PLATFORM_TOOL_REFRESH_INTERVAL", "60"))

    missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if missing:
        logger.warning(
            "platform-gateway: skipping registration - missing env vars: %s",
            ", ".join(missing),
        )
        return

    try:
        from hermes_platform_gateway.client import fetch_tools
        raw_tools = fetch_tools(
            base_url,
            space_id,
            channel_id,
            api_key,
            configuration_id=configuration_id,
        )
    except Exception as exc:
        logger.warning("platform-gateway: could not fetch tools - %s", exc)
        return

    # _current_turn holds the AGENT_START event that triggered the current
    # relay-driven turn so that streaming events and AGENT_END carry matching
    # correlation IDs (author, interaction_id, turn_id, event_id).
    _turn_lock = threading.Lock()
    _current_turn: list[Any] = [None]  # [BaseEvent | None]

    def _on_agent_start(event: Any) -> None:
        text = _extract_user_text(event)
        if not text:
            logger.warning("platform-gateway: AGENT_START with no extractable text, skipping")
            return
        with _turn_lock:
            _current_turn[0] = event
        if not ctx.inject_message(text):
            logger.warning("platform-gateway: inject_message failed (no CLI ref)")
            return
        logger.debug("platform-gateway: injected user message from relay")

    try:
        from hermes_platform_gateway.client import GatewayConnection, build_ws_url
        ws_url = build_ws_url(base_url)
        headers = {"channel-id": channel_id, "space-id": space_id, "api-key": api_key}
        def _on_stop() -> None:
            logger.info("platform-gateway: injecting /stop to interrupt current generation")
            ctx.inject_message("/stop")

        gateway = GatewayConnection(
            ws_url=ws_url,
            headers=headers,
            timeout=timeout,
            on_agent_start=_on_agent_start,
            on_stop=_on_stop,
        )
        gateway.start()
    except Exception as exc:
        logger.warning("platform-gateway: could not start WebSocket connection - %s", exc)
        return

    from hermes_platform_gateway.schema import convert_schema

    registered_names: set[str] = set()
    for tool_def in raw_tools:
        name = tool_def.get("name")
        if not name:
            logger.warning(
                "platform-gateway: skipping tool with missing 'name': %r", tool_def
            )
            continue

        try:
            schema = convert_schema(tool_def)
        except Exception as exc:
            logger.warning(
                "platform-gateway: skipping tool '%s' - schema error: %s", name, exc
            )
            continue

        ctx.register_tool(
            name=name,
            toolset="platform",
            schema=schema,
            handler=_make_handler(gateway, name, _current_turn, _turn_lock),
            is_async=False,
        )
        registered_names.add(name)
        logger.debug("platform-gateway: registered tool '%s'", name)

    logger.info("platform-gateway: registered %d platform tool(s)", len(registered_names))

    if refresh_interval > 0:
        from hermes_platform_gateway.client import RefreshLoop
        RefreshLoop(
            ctx=ctx,
            handler_factory=lambda name: _make_handler(
                gateway, name, _current_turn, _turn_lock
            ),
            base_url=base_url,
            space_id=space_id,
            channel_id=channel_id,
            api_key=api_key,
            interval=refresh_interval,
            initial_names=registered_names,
            configuration_id=configuration_id,
        ).start()
        logger.debug("platform-gateway: canvas polling every %.0fs", refresh_interval)

    # --- Bidirectional relay hook --------------------------------------------
    #
    # We deliberately do NOT stream tokens as RESPONSE(is_partial=True) events:
    # the platform's relay treats each RESPONSE as its own block and joins
    # them with newlines in the UI (and a non-empty AGENT_END would get
    # promoted into a *second* full message via the
    # "[DelegateAgent] Promoting AGENT_END with content to final RESPONSE"
    # path). Instead we deliver one final AGENT_END carrying the full
    # assistant text — same shape `domyn expose`'s Runtime uses.

    def _on_turn_complete(
        assistant_response: str = "",
        session_id: str | None = None,
        **_: Any,
    ) -> None:
        from domyn_agents.core import BaseEvent, ExecutionEventType, Part
        with _turn_lock:
            turn = _current_turn[0]
            _current_turn[0] = None
        if turn is None:
            return
        if gateway._stop_requested.is_set():
            logger.info("platform-gateway: turn cancelled by user, sending stop acknowledgement")
            gateway._stop_requested.clear()
            assistant_response = "Response stopped as requested."
        event = BaseEvent(
            event_type=ExecutionEventType.AGENT_END,
            author=turn.author,
            event_id=turn.event_id,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            content=[Part(text=assistant_response)] if assistant_response else [],
        )
        gateway.send_event(event)
        logger.debug("platform-gateway: sent AGENT_END for turn %s", turn.event_id)

    ctx.register_hook("post_llm_call", _on_turn_complete)


def _make_handler(
    gateway: Any,
    tool_name: str,
    current_turn: list[Any],
    turn_lock: threading.Lock,
) -> Any:
    def handler(args: dict, **kwargs: Any) -> str:
        with turn_lock:
            turn = current_turn[0]
        return gateway.call_tool(tool_name, args, turn=turn, **kwargs)
    return handler


def _extract_user_text(event: Any) -> str:
    """Extract plain user text from an AGENT_START relay event."""
    if event.action and event.action.parameters:
        params = event.action.parameters
        for key in ("input", "text", "message", "content"):
            val = params.get(key)
            if isinstance(val, str) and val:
                return val
    for part in event.content or []:
        if getattr(part, "text", None):
            return part.text
    if event.action and event.action.parameters:
        return json.dumps(event.action.parameters)
    return ""
