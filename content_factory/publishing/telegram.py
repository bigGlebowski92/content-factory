"""Telegram publishing clients for Stage 2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TelegramClient(ABC):
    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """Send a message; return Telegram-like API response."""


class MockTelegramClient(TelegramClient):
    """In-memory Telegram client for tests — no network, no real bot."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        message_id = str(len(self.sent_messages) + 1)
        record = {
            "chat_id": chat_id,
            "text": text,
            "message_id": message_id,
        }
        self.sent_messages.append(record)
        return {
            "ok": True,
            "result": {
                "message_id": message_id,
                "chat": {"id": chat_id},
                "text": text,
            },
        }


class HttpTelegramClient(TelegramClient):
    """Real Telegram Bot API client (used only when mock is disabled)."""

    def __init__(self, bot_token: str) -> None:
        if not bot_token:
            raise ValueError("telegram bot token is required")
        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_base}/sendMessage",
                json={"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("description", "Telegram API error"))
            return payload


def get_telegram_client(*, use_mock: bool = True, bot_token: str = "") -> TelegramClient:
    if use_mock:
        return MockTelegramClient()
    return HttpTelegramClient(bot_token)
