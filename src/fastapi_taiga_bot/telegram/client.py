from functools import lru_cache

import httpx

from fastapi_taiga_bot.config import get_settings


class TelegramClient:
    def __init__(self):
        settings = get_settings()
        self._base_url: str = f"https://api.telegram.org/bot{settings.telegram_token}"
        self._client = httpx.AsyncClient()


    async def send_message(self, chat_id: int, text: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text
            }
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()


@lru_cache
def get_telegram_client() -> TelegramClient:
    return TelegramClient()