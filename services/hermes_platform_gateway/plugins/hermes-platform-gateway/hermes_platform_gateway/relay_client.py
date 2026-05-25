"""Domyn relay WebSocket client.

Pure transport: framing, connect, send_event, receive-loop dispatch.
No business logic — adapter.py owns event routing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


def _backoff_delay(attempt: int, *, rng: Callable[[], float] = random.random) -> float:
    """Full-jitter exponential backoff.

    delay = min(30, 0.5 * 2**attempt) * (0.5 + 0.5 * rng())
    """
    base = min(30.0, 0.5 * (2**attempt))
    return base * (0.5 + 0.5 * rng())


class DomynRelayClient:
    """Async WebSocket client for the Domyn relay.

    Owns the connect/reconnect loop and exposes ``send_event`` for outbound
    frames. Inbound frames are passed to a caller-supplied async callback.
    """

    def __init__(
        self,
        ws_url: str,
        headers: dict[str, str],
        on_event: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._headers = headers
        self._on_event = on_event
        self._ws: Any = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def send_event(self, event: Any) -> None:
        from domyn_agents.core import RelayMessage

        if self._ws is None:
            raise RuntimeError("DomynRelayClient: not connected")
        msg = RelayMessage(payload=event).model_dump_json()
        # Full outbound frame at WARNING so we can see exactly what hits the
        # wire (event_type, correlation IDs, thought/text parts). Truncate to
        # 1000 chars so long observations don't drown the log.
        logger.warning("DomynRelayClient: outbound %s", msg[:1000])
        await self._ws.send(msg)

    async def _consume(self, ws: Any) -> None:
        """Iterate frames, parse RelayMessage, dispatch to on_event."""
        from domyn_agents.core import RelayMessage

        async for raw in ws:
            try:
                msg = RelayMessage.model_validate_json(raw)
            except Exception as exc:
                # Include the raw frame (truncated) so timeouts caused by
                # silently-dropped TOOL_END frames can be diagnosed. The
                # platform's schema sometimes diverges from domyn-agents'
                # ToolAction (e.g. missing/extra fields).
                logger.warning(
                    "DomynRelayClient: dropping malformed frame: %s | raw=%s",
                    str(exc)[:200],
                    str(raw)[:500],
                )
                continue
            if self._on_event is None:
                continue
            try:
                await self._on_event(msg.payload)
            except Exception as exc:
                logger.warning("DomynRelayClient: on_event raised: %s", exc)

    async def connect(self) -> None:
        """Spawn the connect loop task. Returns immediately."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._connect_loop())

    async def disconnect(self) -> None:
        """Stop the connect loop and close the active socket."""
        self._stop.set()
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def _connect_loop(self) -> None:
        import websockets

        attempt = 0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._ws_url, additional_headers=self._headers) as ws:
                    self._ws = ws
                    attempt = 0
                    await self._consume(ws)
            except Exception as exc:
                logger.warning("DomynRelayClient: connection error - %s", exc)
            finally:
                self._ws = None

            if self._stop.is_set():
                break

            delay = _backoff_delay(attempt)
            logger.debug("DomynRelayClient: reconnecting in %.1fs", delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
                break  # stop requested during sleep
            except TimeoutError:
                pass
            attempt = min(attempt + 1, 6)
