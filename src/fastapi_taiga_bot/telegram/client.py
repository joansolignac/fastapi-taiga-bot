from functools import lru_cache

import httpx

from fastapi_taiga_bot.config import get_settings


class TelegramClient:
    def __init__(self):
        settings = get_settings()
        self._base_url: str = f"https://api.telegram.org/bot{settings.telegram_token}"
        self._client = httpx.AsyncClient()


    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        response = await self._client.post(
            f"{self._base_url}/sendMessage",
            json=payload
        )
        response.raise_for_status()

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        response = await self._client.post(
            f"{self._base_url}/editMessageText",
            json=payload
        )
        if response.status_code == 400 and "message is not modified" in response.text:
            return
        response.raise_for_status()

    async def answer_callback_query(self, callback_query_id: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id}
        )
        response.raise_for_status()

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        response = await self._client.post(
            f"{self._base_url}/deleteMessage",
            json={
                "chat_id": chat_id,
                "message_id": message_id
            }
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


@lru_cache
def get_telegram_client() -> TelegramClient:
    return TelegramClient()