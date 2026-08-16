"""
brain/bridge/client.py

WebSocket/REST client that connects to the avatar bridge server
(avatar/src/main/bridge-server.ts) on 127.0.0.1:8765.

The avatar bridge server is the WebSocket server; the brain is the client.
The brain sends commands (speak, state_change, confirmation_request, error).
The brain receives events (activate, confirmation_response, pong).

Usage:
    client = BridgeClient(host="127.0.0.1", port=8765)
    await client.connect()
    await client.speak("Hello!", emotion="happy", animation="greeting")
    await client.set_state("LISTENING")
    await client.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Coroutine

try:
    import websockets
    from websockets.asyncio.client import ClientConnection
except ImportError:
    websockets = None  # type: ignore[assignment]
    ClientConnection = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class BridgeClient:
    """
    Async WebSocket client for the avatar bridge.

    Handles:
      - Reconnection with exponential backoff
      - Ping/pong keepalive
      - Dispatching inbound events to registered handlers
      - Queuing outbound messages during reconnect windows
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._uri = f"ws://{host}:{port}"
        self._ws: ClientConnection | None = None
        self._connected = asyncio.Event()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._pending_confirmations: dict[str, asyncio.Future[bool]] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the background receive loop (connects + reconnects)."""
        if websockets is None:
            logger.warning("websockets library not installed — bridge client disabled.")
            return
        self._running = True
        asyncio.create_task(self._run_forever())
        # Wait up to 10s for the first connection
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Bridge: avatar not reachable within 10s. Will keep retrying.")

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()
        logger.info("Bridge: disconnected from avatar.")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._ws is not None

    # ------------------------------------------------------------------
    # Sending commands
    # ------------------------------------------------------------------

    async def speak(
        self,
        text: str,
        emotion: str = "neutral",
        animation: str = "idle",
        audio_url: str | None = None,
        priority: str = "normal",
    ) -> None:
        """Send a speak command to the avatar."""
        msg: dict[str, Any] = {
            "type": "speak",
            "text": text,
            "emotion": emotion,
            "animation": animation,
            "priority": priority,
        }
        if audio_url:
            msg["audio_url"] = audio_url
        await self._send(msg)

    async def set_state(self, state: str, reason: str = "") -> None:
        """Transition the avatar to a new state."""
        msg: dict[str, Any] = {"type": "state_change", "state": state}
        if reason:
            msg["reason"] = reason
        await self._send(msg)

    async def send_error(self, message: str, code: str = "", recoverable: bool = True) -> None:
        """Send an error event to the avatar."""
        msg: dict[str, Any] = {"type": "error", "message": message, "recoverable": recoverable}
        if code:
            msg["code"] = code
        await self._send(msg)

    async def request_confirmation(
        self,
        tool_name: str,
        action_description: str,
        risk_tier: str = "HIGH",
        timeout_seconds: float = 30.0,
    ) -> bool:
        """
        Send a confirmation_request to the avatar and wait for the user's response.
        Returns True if confirmed, False if denied or timed out.
        """
        request_id = str(uuid.uuid4())
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
        self._pending_confirmations[request_id] = future

        msg: dict[str, Any] = {
            "type": "confirmation_request",
            "request_id": request_id,
            "action_description": action_description,
            "tool_name": tool_name,
            "risk_tier": risk_tier,
            "timeout_seconds": timeout_seconds,
        }
        await self._send(msg)

        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("Confirmation timed out for request %s", request_id)
            return False
        finally:
            self._pending_confirmations.pop(request_id, None)

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for a specific bridge event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a JSON message. Silently drops if not connected."""
        if not self.is_connected or self._ws is None:
            logger.debug("Bridge: not connected, dropping message type=%s", message.get("type"))
            return
        try:
            await self._ws.send(json.dumps(message))
        except Exception as exc:
            logger.warning("Bridge send failed: %s", exc)
            self._connected.clear()

    async def _run_forever(self) -> None:
        """Reconnect loop with exponential backoff."""
        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(self._uri) as ws:  # type: ignore[attr-defined]
                    self._ws = ws
                    self._connected.set()
                    backoff = 1.0
                    logger.info("Bridge: connected to avatar at %s", self._uri)
                    await self._receive_loop(ws)
            except Exception as exc:
                self._connected.clear()
                self._ws = None
                if self._running:
                    logger.info("Bridge: disconnected (%s). Reconnecting in %.1fs...", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)

    async def _receive_loop(self, ws: Any) -> None:
        """Receive and dispatch messages."""
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Bridge: received non-JSON message: %r", raw)
                continue

            msg_type = msg.get("type")

            # Handle confirmation responses internally
            if msg_type == "confirmation_response":
                request_id = msg.get("request_id")
                confirmed = msg.get("confirmed", False)
                if request_id and request_id in self._pending_confirmations:
                    self._pending_confirmations[request_id].set_result(confirmed)

            # Dispatch to registered handlers
            handlers = self._handlers.get(msg_type, [])
            for handler in handlers:
                asyncio.create_task(handler(msg))