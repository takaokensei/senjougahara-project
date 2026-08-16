"""
brain/tests/test_telegram_approval.py

Unit tests for TelegramApprovalChannel and message parsing.
"""

from __future__ import annotations

import pytest
import httpx

from brain.comms.telegram_approval import (
    TelegramApprovalChannel,
    parse_approval_reply,
)


class TestTelegramApproval:
    def test_parse_approval_reply(self):
        req_id = "abcd1234-5678-90ef-ghij-klmnopqrstuv"
        short_id = "abcd1234"

        # Valid approvals
        assert parse_approval_reply("aprovar abcd1234", req_id) is True
        assert parse_approval_reply("Aprovo abcd1234", req_id) is True
        assert parse_approval_reply(f"approve {req_id}", req_id) is True
        assert parse_approval_reply("Sim, abcd1234", req_id) is True
        assert parse_approval_reply("confirmar abcd1234", req_id) is True

        # Valid denials
        assert parse_approval_reply("negar abcd1234", req_id) is False
        assert parse_approval_reply("Nego abcd1234", req_id) is False
        assert parse_approval_reply(f"deny {req_id}", req_id) is False
        assert parse_approval_reply("rejeitar abcd1234", req_id) is False
        assert parse_approval_reply("não abcd1234", req_id) is False

        # Irrelevant or wrong ID
        assert parse_approval_reply("aprovar 99999999", req_id) is None
        assert parse_approval_reply("olá mundo", req_id) is None
        assert parse_approval_reply("", req_id) is None

    @pytest.mark.asyncio
    async def test_disabled_channel_is_noop(self):
        channel = TelegramApprovalChannel(enabled=False)
        assert channel.is_active is False
        assert await channel.send_approval_request("id1", "tool1", "HIGH", "desc") is False
        assert await channel.poll_for_decision("id1", timeout_s=0.1) is None

    @pytest.mark.asyncio
    async def test_mocked_telegram_flow(self):
        req_id = "test-req-12345"

        def mock_handler(request: httpx.Request):
            if "sendMessage" in str(request.url):
                return httpx.Response(200, json={"ok": True, "result": {"message_id": 100}})
            elif "getUpdates" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "result": [
                            {
                                "update_id": 1,
                                "message": {
                                    "chat": {"id": 123456},
                                    "text": f"aprovar {req_id}",
                                },
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(mock_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            channel = TelegramApprovalChannel(
                bot_token="123456:ABC-DEF",
                chat_id="123456",
                enabled=True,
                client=client,
            )
            assert channel.is_active is True

            sent = await channel.send_approval_request(
                request_id=req_id,
                tool_name="delete_file",
                risk_tier="HIGH",
                action_description="Delete old log",
            )
            assert sent is True

            decision = await channel.poll_for_decision(request_id=req_id, timeout_s=2.0)
            assert decision is True
