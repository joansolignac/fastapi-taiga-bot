from functools import lru_cache
from typing import Awaitable, Callable, TypeVar

import httpx

from fastapi_taiga_bot.config import get_settings
from fastapi_taiga_bot.taiga.client import TaigaClient, get_taiga_client

T = TypeVar("T")


class TaigaAdminService:
    """Taiga service account driven by the credentials in the environment.

    Unlike a user's TaigaSession, these tokens live only in memory: the
    credentials are always available, so a failed refresh can fall back to a
    full re-login instead of needing encrypted persistence.
    """

    def __init__(self, taiga_client: TaigaClient):
        self._taiga_client = taiga_client
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user_id: int | None = None

    async def get_admin_user_id(self) -> int:
        if self._user_id is None:
            await self._login()
        return self._user_id

    async def list_open_user_stories(self) -> list[dict]:
        return await self.call_with_valid_token(self._taiga_client.list_all_open_user_stories)

    async def call_with_valid_token(self, call: Callable[[str], Awaitable[T]]) -> T:
        if self._access_token is None:
            await self._login()

        try:
            return await call(self._access_token)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 401:
                raise

            await self._reauthenticate()
            return await call(self._access_token)

    async def _reauthenticate(self) -> None:
        try:
            auth_data = await self._taiga_client.refresh_token(self._refresh_token)
        except httpx.HTTPStatusError:
            # The refresh token expired too; the credentials are in the
            # environment, so a full re-login is always available.
            await self._login()
            return

        self._store(auth_data)

    async def _login(self) -> None:
        settings = get_settings()
        auth_data = await self._taiga_client.login(
            settings.taiga_admin_username, settings.taiga_admin_password
        )
        self._store(auth_data)

        user = await self._taiga_client.me(self._access_token)
        self._user_id = user["id"]

    def _store(self, auth_data: dict) -> None:
        self._access_token = auth_data["auth_token"]
        self._refresh_token = auth_data["refresh"]


@lru_cache
def get_taiga_admin_service() -> TaigaAdminService:
    return TaigaAdminService(get_taiga_client())
