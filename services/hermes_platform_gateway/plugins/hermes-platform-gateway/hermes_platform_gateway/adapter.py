"""DomynPlatformAdapter — gateway-mode bridge to the Domyn relay.

Per turn:
    AGENT_START (in) → STARTED (out) → handle_message dispatch
                    → (tool calls round-trip via the relay)
                    → AGENT_END (out, one per visible chat message)
                    → END (out, exactly once, from on_processing_complete)

Per platform tool call:
    pre_tool_call hook stashes (chat_id, thought) by task_id
    tool handler calls adapter.call_tool(session_key, tool_name, args, thought)
    adapter emits TOOL_START, awaits TOOL_END/TOOL_ERROR from the relay
    _resolve_tool_call wakes the awaiting handler via call_soon_threadsafe
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from gateway.config import Platform, PlatformConfig
from gateway.platform_registry import PlatformEntry, platform_registry
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)
from gateway.session import SessionSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _build_session_key(channel_id: str, conversation_id: str) -> str:
    return f"domyn:{channel_id}:{conversation_id}"


def _extract_user_text(event: Any) -> str:
    """Pull plain user text out of an AGENT_START relay event."""
    action = getattr(event, "action", None)
    params = getattr(action, "parameters", None) if action else None
    if params:
        for key in ("input", "text", "message", "content"):
            val = params.get(key)
            if isinstance(val, str) and val:
                return val
    for part in getattr(event, "content", None) or []:
        text = getattr(part, "text", None)
        if text:
            return text
    if params:
        return json.dumps(params)
    return ""


def _serialise_observation(observation: Any) -> str:
    """Return *observation* as a JSON string (passthrough if already valid JSON)."""
    if isinstance(observation, str):
        try:
            json.loads(observation)
            return observation
        except json.JSONDecodeError:
            pass
    return json.dumps(observation)


# Register "domyn" as a dynamic Platform value so ``Platform("domyn")``
# resolves via the enum's _missing_() hook at adapter construction time.
# Module-level side-effect because we need it before any DomynPlatformAdapter
# instance is built (including the standalone test ones that don't go
# through ctx.register_platform).
def _ensure_domyn_registered() -> None:
    if not platform_registry.is_registered("domyn"):
        platform_registry.register(
            PlatformEntry(
                name="domyn",
                label="Domyn",
                adapter_factory=lambda cfg: None,
                check_fn=lambda: True,
            )
        )


_ensure_domyn_registered()


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class DomynPlatformAdapter(BasePlatformAdapter):
    """Bridges the Domyn relay WebSocket to hermes' gateway runner."""

    # =====================================================================
    # Lifecycle (BasePlatformAdapter contract)
    # =====================================================================

    def __init__(
        self,
        config: PlatformConfig,
        *,
        channel_id: str,
        relay_client_factory: Callable[[Callable[[Any], Any]], Any],
    ) -> None:
        super().__init__(config=config, platform=Platform("domyn"))
        self._channel_id = channel_id
        # Per-conversation state — keyed by adapter-internal session_key.
        self._turn_by_session: dict[str, Any] = {}
        # Per-tool-call state — keyed by hermes' registry task_id.
        self._chat_id_by_task: dict[str, str] = {}
        self._thought_by_task: dict[str, str] = {}
        # Per-call_id state — for visibility (built-in tools) vs real
        # platform tool round-trips. Disjoint keyspaces.
        self._visibility_call_id_by_task: dict[str, str] = {}
        self._pending_calls: dict[str, Any] = {}  # call_id -> (Future, loop)
        self._client = relay_client_factory(self._on_event)

    async def connect(self) -> bool:
        await self._client.connect()
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        await self._client.disconnect()
        self._fail_pending("disconnect")
        self._mark_disconnected()

    async def send_typing(self, chat_id: str, metadata: Any = None) -> None:
        return None

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        return {"name": chat_id, "type": "dm", "chat_id": chat_id}

    async def on_processing_complete(self, event: MessageEvent, outcome: Any) -> None:
        """Emit the terminal END *after* the gateway's final send returns.

        ``BasePlatformAdapter._process_message_background`` calls this
        hook after the final ``adapter.send`` returns (see
        ``gateway/platforms/base.py:2964``), so it's the only place we
        can emit END *after* the final AGENT_END rather than before.
        """
        chat_id = getattr(getattr(event, "source", None), "chat_id", None)
        if not chat_id:
            return
        turn = self._turn_by_session.get(_build_session_key(self._channel_id, chat_id))
        if turn is None:
            return
        await self.emit_end(turn=turn)

    # =====================================================================
    # Inbound events from the relay
    # =====================================================================

    async def _on_event(self, event: Any) -> None:
        from domyn_agents.core import ExecutionEventType

        et = getattr(event, "event_type", None)
        logger.debug(
            "domyn-adapter: inbound event type=%s conversation_id=%s call_id=%s",
            getattr(et, "value", et),
            getattr(event, "conversation_id", None),
            getattr(getattr(event, "action", None), "call_id", None),
        )
        if et == ExecutionEventType.AGENT_START:
            await self._handle_agent_start(event)
            return
        if et in (ExecutionEventType.TOOL_END, ExecutionEventType.TOOL_ERROR):
            self._resolve_tool_call(event)

    async def _handle_agent_start(self, event: Any) -> None:
        conv_id = getattr(event, "conversation_id", None)
        if not conv_id:
            logger.warning("domyn-adapter: AGENT_START missing conversation_id, dropping")
            return
        text = _extract_user_text(event)
        if not text:
            logger.warning("domyn-adapter: AGENT_START with no extractable text, dropping")
            return

        self._turn_by_session[_build_session_key(self._channel_id, conv_id)] = event

        # Bookend: STARTED tells the UI "received, working" — sent
        # BEFORE handle_message dispatches into the gateway so the
        # signal is visible even on long first turns.
        await self.emit_started(turn=event)

        source = SessionSource(
            platform=Platform("domyn"),
            chat_id=conv_id,
            chat_name=conv_id,
            chat_type="dm",
            user_id=getattr(event, "author", None),
            user_name=getattr(event, "author", None),
        )
        msg = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=getattr(event, "event_id", None),
            timestamp=datetime.now(),
        )
        await self.handle_message(msg)

    # =====================================================================
    # Outbound emits
    # =====================================================================

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Emit AGENT_END for one visible chat message.

        Called multiple times per turn (interim narrative, "⏳ Still
        working…" notifiers, the final reply). END is NOT emitted here
        — that's per-turn, fired from ``on_processing_complete``.
        """
        from domyn_agents.core import BaseEvent, ExecutionEventType, Part

        session_key = _build_session_key(self._channel_id, chat_id)
        turn = self._turn_by_session.get(session_key)
        if turn is None:
            preview = (content or "")[:100]
            logger.warning(
                "domyn-adapter: send for %s with no prior AGENT_START (preview=%r)",
                session_key,
                preview,
            )
            return SendResult(success=False, error="no prior AGENT_START")

        # event_id is per-frame unique; let BaseEvent auto-generate.
        # Copying turn.event_id collides with TOOL_START (also fires
        # against the same turn) and confuses platforms that key on it.
        event = BaseEvent(
            event_type=ExecutionEventType.AGENT_END,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            content=[Part(text=content)] if content else [],
        )
        try:
            await self._client.send_event(event)
        except Exception as exc:
            logger.warning("domyn-adapter: send_event failed - %s", exc)
            return SendResult(success=False, error=str(exc), retryable=True)
        return SendResult(success=True, message_id=event.event_id)

    async def emit_started(self, *, turn: Any) -> None:
        """Push STARTED on AGENT_START receipt (fire-and-forget)."""
        from domyn_agents.core import BaseEvent, ExecutionEventType

        event = BaseEvent(
            event_type=ExecutionEventType.STARTED,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
        )
        try:
            await self._client.send_event(event)
        except Exception as exc:
            logger.warning("domyn-adapter: emit_started failed - %s", exc)

    async def emit_end(self, *, turn: Any) -> None:
        """Push END once per turn after AGENT_END has been delivered."""
        from domyn_agents.core import BaseEvent, ExecutionEventType

        event = BaseEvent(
            event_type=ExecutionEventType.END,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
        )
        try:
            await self._client.send_event(event)
        except Exception as exc:
            logger.warning("domyn-adapter: emit_end failed - %s", exc)

    async def emit_visibility_tool_start(
        self,
        *,
        chat_id: str,
        tool_name: str,
        args: dict[str, Any],
        thought: str | None,
        call_id: str,
    ) -> None:
        """Push TOOL_START for a hermes built-in tool (visibility only).

        No pending future is registered and no TOOL_END round-trip is
        expected from the platform — the matching TOOL_END is emitted by
        ``emit_visibility_tool_end`` from the post_tool_call hook.
        """
        from domyn_agents.core import BaseEvent, ExecutionEventType, ToolAction

        turn = self._turn_by_session.get(_build_session_key(self._channel_id, chat_id))
        if turn is None:
            return
        event = BaseEvent(
            event_type=ExecutionEventType.TOOL_START,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            action=ToolAction(
                name=tool_name,
                parameters=args or {},
                call_id=call_id,
                thought=thought,
            ),
        )
        try:
            await self._client.send_event(event)
        except Exception as exc:
            logger.warning(
                "domyn-adapter: emit_visibility_tool_start %s failed - %s",
                tool_name,
                exc,
            )

    async def emit_visibility_tool_end(
        self,
        *,
        chat_id: str,
        tool_name: str,
        call_id: str,
        observation: Any,
    ) -> None:
        """Push TOOL_END for a hermes built-in tool (companion to start)."""
        from domyn_agents.core import BaseEvent, ExecutionEventType, ToolAction

        turn = self._turn_by_session.get(_build_session_key(self._channel_id, chat_id))
        if turn is None:
            return
        event = BaseEvent(
            event_type=ExecutionEventType.TOOL_END,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            action=ToolAction(
                name=tool_name,
                parameters={},
                call_id=call_id,
                observation=observation,
            ),
        )
        try:
            await self._client.send_event(event)
        except Exception as exc:
            logger.warning(
                "domyn-adapter: emit_visibility_tool_end %s failed - %s",
                tool_name,
                exc,
            )

    # =====================================================================
    # Tool-call routing (real platform tools — round-trip via the relay)
    # =====================================================================

    async def call_tool(
        self,
        *,
        session_key: str,
        tool_name: str,
        args: dict[str, Any],
        thought: str | None = None,
        timeout: float = 120.0,
    ) -> str:
        """Send TOOL_START, await TOOL_END/TOOL_ERROR, return the observation as JSON."""
        from domyn_agents.core import BaseEvent, ExecutionEventType, ToolAction

        turn = self._turn_by_session.get(session_key)
        if turn is None:
            return json.dumps({"error": "no active turn for session"})

        call_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        # Stash (future, loop) — _resolve_tool_call runs on the relay
        # client's loop, which may differ from this one, so we'll need
        # call_soon_threadsafe to wake the awaiter.
        self._pending_calls[call_id] = (fut, loop)

        start = BaseEvent(
            event_type=ExecutionEventType.TOOL_START,
            author=turn.author,
            interaction_id=turn.interaction_id,
            turn_id=turn.turn_id,
            conversation_id=turn.conversation_id,
            action=ToolAction(
                name=tool_name,
                parameters=args,
                call_id=call_id,
                thought=thought,
            ),
        )
        logger.debug(
            "domyn-adapter: TOOL_START name=%s call_id=%s conversation_id=%s",
            tool_name,
            call_id,
            turn.conversation_id,
        )
        try:
            await self._client.send_event(start)
        except Exception as exc:
            self._pending_calls.pop(call_id, None)
            logger.warning(
                "domyn-adapter: TOOL_START send failed for %s call_id=%s - %s",
                tool_name,
                call_id,
                exc,
            )
            return json.dumps({"error": f"send failed: {exc}"})

        try:
            observation = await asyncio.wait_for(fut, timeout=timeout)
            logger.debug(
                "domyn-adapter: TOOL_END received name=%s call_id=%s",
                tool_name,
                call_id,
            )
            return _serialise_observation(observation)
        except TimeoutError:
            self._pending_calls.pop(call_id, None)
            logger.warning(
                "domyn-adapter: TOOL timeout name=%s call_id=%s after %.1fs",
                tool_name,
                call_id,
                timeout,
            )
            return json.dumps({"error": f"Tool '{tool_name}' timed out after {timeout}s"})
        except Exception as exc:
            logger.warning(
                "domyn-adapter: TOOL future raised name=%s call_id=%s - %s",
                tool_name,
                call_id,
                exc,
            )
            return json.dumps({"error": str(exc)})

    def _resolve_tool_call(self, event: Any) -> None:
        """Wake the awaiter in call_tool when TOOL_END/TOOL_ERROR arrives."""
        from domyn_agents.core import ExecutionEventType

        et_value = getattr(event.event_type, "value", event.event_type)
        call_id = getattr(getattr(event, "action", None), "call_id", None)
        if not call_id:
            logger.warning("domyn-adapter: %s with no call_id, dropping", et_value)
            return
        entry = self._pending_calls.pop(call_id, None)
        if entry is None:
            logger.warning(
                "domyn-adapter: %s call_id=%s has no pending future (pending=%s)",
                et_value,
                call_id,
                sorted(self._pending_calls.keys()),
            )
            return
        fut, fut_loop = entry
        if fut.done():
            logger.warning(
                "domyn-adapter: %s call_id=%s future already resolved",
                et_value,
                call_id,
            )
            return
        if event.event_type == ExecutionEventType.TOOL_ERROR:
            msg = (
                getattr(event, "error_message", None)
                or f"platform tool error ({getattr(event, 'error_code', '')})"
            )
            self._resolve_future(fut, fut_loop, exc=RuntimeError(msg))
        else:
            observation = getattr(getattr(event, "action", None), "observation", None)
            self._resolve_future(fut, fut_loop, result=observation)

    def _fail_pending(self, reason: str) -> None:
        """Fail every in-flight tool call — called on disconnect."""
        for fut, fut_loop in self._pending_calls.values():
            if fut.done():
                continue
            fut_loop.call_soon_threadsafe(fut.set_exception, RuntimeError(reason))
        self._pending_calls.clear()

    @staticmethod
    def _resolve_future(
        fut: asyncio.Future,
        fut_loop: asyncio.AbstractEventLoop,
        *,
        result: Any = None,
        exc: BaseException | None = None,
    ) -> None:
        """Resolve a Future from a potentially different event loop.

        The future is bound to the loop where ``call_tool`` ran (a
        worker loop spawned by hermes' ``_run_async``). The relay
        receive loop, which calls us, runs in the gateway's loop.
        ``call_soon_threadsafe`` is the canonical cross-loop bridge.
        """

        def _apply() -> None:
            if fut.done():
                return
            if exc is not None:
                fut.set_exception(exc)
            else:
                fut.set_result(result)

        # Worker loop closed already — nothing waiting.
        with contextlib.suppress(RuntimeError):
            fut_loop.call_soon_threadsafe(_apply)

    # =====================================================================
    # Per-task bookkeeping (used by pre_tool_call / post_tool_call hooks)
    # =====================================================================

    def session_key_for_chat(self, chat_id: str) -> str:
        """Derive the adapter's internal session_key from a chat_id."""
        return _build_session_key(self._channel_id, chat_id)

    def record_task_chat(self, *, task_id: str, chat_id: str, thought: str | None = None) -> None:
        """Stash (chat_id, thought) for a registry task_id.

        The platform tool handler only receives ``task_id`` from
        ``registry.dispatch`` (not ``parent_agent``), so the
        pre_tool_call hook stores the chat_id under task_id here and the
        handler reads it back. The optional ``thought`` rides on
        ``ToolAction.thought`` so the platform can render *why* the tool
        was invoked.
        """
        if task_id and chat_id:
            self._chat_id_by_task[task_id] = chat_id
            if thought:
                self._thought_by_task[task_id] = thought

    def forget_task(self, *, task_id: str) -> None:
        """Drop the per-task stashes after the tool finishes."""
        if task_id:
            self._chat_id_by_task.pop(task_id, None)
            self._thought_by_task.pop(task_id, None)

    def thought_for_task(self, task_id: str) -> str | None:
        """Return the thought stashed by pre_tool_call, if any."""
        return self._thought_by_task.get(task_id)

    def record_visibility_call(self, *, task_id: str, call_id: str) -> None:
        """Pair a visibility TOOL_START's call_id with task_id for post_tool_call."""
        if task_id and call_id:
            self._visibility_call_id_by_task[task_id] = call_id

    def pop_visibility_call(self, task_id: str) -> str | None:
        """Return-and-clear the visibility call_id for *task_id*."""
        return self._visibility_call_id_by_task.pop(task_id, None) if task_id else None
