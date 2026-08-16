"""
brain/comms/telegram_approval.py

Remote approval delivery channel via Telegram bot.

Inspired by the approval-delivery and telegram channel patterns in vierisid/jarvis
(studied as architectural reference only, not code-copied; RSALv2 license).
Reimplemented independently in Python.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def parse_approval_reply(text: str, request_id: str) -> bool | None:
    """
    Parse an incoming message text to see if it is an approval or denial for request_id.
    Matches full request_id or short 8-char prefix.
    """
    text_clean = text.strip().lower()
    short_id = request_id[:8].lower() if len(request_id) >= 8 else request_id.lower()
    target_id = request_id.lower()

    # Check if request_id or short_id is referenced
    if target_id not in text_clean and short_id not in text_clean:
        return None

    # Positive approval keywords
    if re.search(r"\b(aprovar|aprovo|approve|approved|sim|confirmar|confirmo|yes|ok)\b", text_clean):
        return True

    # Negative rejection keywords
    if re.search(r"\b(negar|nego|deny|denied|rejeitar|rejeito|recusar|recuso|não|nao|no)\b", text_clean):
        return False

    return None


class TelegramApprovalChannel:
    """
    Sends tool confirmation requests to a Telegram chat and polls for responses.
    Operates as a silent no-op when disabled or unconfigured.
    """

    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
        enabled: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.enabled = enabled
        self._client = client
        self._last_update_id: int = 0

    @property
    def is_active(self) -> bool:
        return bool(self.enabled and self.bot_token and self.chat_id)

    def _get_api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    async def send_approval_request(
        self,
        request_id: str,
        tool_name: str,
        risk_tier: str,
        action_description: str,
    ) -> bool:
        """Send an approval prompt to the configured Telegram chat."""
        if not self.is_active:
            return False

        short_id = request_id[:8]
        message_text = (
            f"⚠️ *Confirmação de Ação [{risk_tier}]*\n\n"
            f"🔧 *Tool:* `{tool_name}`\n"
            f"📝 *Ação:* {action_description}\n"
            f"🔑 *ID:* `{short_id}`\n\n"
            f"Para responder, envie:\n"
            f"👉 `aprovar {short_id}`\n"
            f"👉 `negar {short_id}`"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "Markdown",
        }

        try:
            if self._client:
                resp = await self._client.post(self._get_api_url("sendMessage"), json=payload, timeout=10.0)
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(self._get_api_url("sendMessage"), json=payload, timeout=10.0)
            
            if resp.status_code == 200:
                logger.info("[TELEGRAM] Sent approval request for %s (id: %s)", tool_name, short_id)
                return True
            else:
                logger.warning("[TELEGRAM] Failed sending approval request: %s %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.warning("[TELEGRAM] Request error: %s", exc)
            return False

    async def poll_for_decision(
        self,
        request_id: str,
        timeout_s: float = 30.0,
    ) -> bool | None:
        """
        Poll Telegram for a reply to the specified request_id.
        Returns True (approved), False (denied), or None (timed out).
        """
        if not self.is_active:
            return None

        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            remaining = max(1.0, deadline - time.monotonic())
            poll_timeout = min(5, int(remaining))

            params: dict[str, Any] = {
                "timeout": poll_timeout,
                "allowed_updates": ["message"],
            }
            if self._last_update_id > 0:
                params["offset"] = self._last_update_id + 1

            try:
                if self._client:
                    resp = await self._client.get(
                        self._get_api_url("getUpdates"), params=params, timeout=poll_timeout + 5.0
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            self._get_api_url("getUpdates"), params=params, timeout=poll_timeout + 5.0
                        )

                if resp.status_code == 200:
                    data = resp.json()
                    updates = data.get("result", [])
                    for update in updates:
                        up_id = update.get("update_id", 0)
                        if up_id > self._last_update_id:
                            self._last_update_id = up_id

                        msg = update.get("message", {})
                        from_chat_id = str(msg.get("chat", {}).get("id", ""))
                        text = msg.get("text", "")

                        if from_chat_id == self.chat_id and text:
                            decision = parse_approval_reply(text, request_id)
                            if decision is not None:
                                logger.info(
                                    "[TELEGRAM] Received decision for %s: %s",
                                    request_id,
                                    "APPROVED" if decision else "DENIED",
                                )
                                return decision
            except Exception as exc:
                logger.debug("[TELEGRAM] Poll error: %s", exc)

            await asyncio.sleep(1.0)

        return None
