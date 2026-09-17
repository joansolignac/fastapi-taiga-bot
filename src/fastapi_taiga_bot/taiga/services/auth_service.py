from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.taiga.client import TaigaClient, get_taiga_client
from fastapi_taiga_bot.taiga.models import TaigaSession
from fastapi_taiga_bot.taiga.services.token_cipher import TokenCipher, get_token_cipher

T = TypeVar("T")


class NotLoggedInError(Exception):
    pass


class TaigaAuthService:
    def __init__(self, taiga_client: TaigaClient, cipher: TokenCipher):
        self._taiga_client = taiga_client
        self._cipher = cipher

    async def login(
        self,
        session: AsyncSession,
        chat_id: int,
        telegram_username: str | None,
        email: str,
        password: str,
    ) -> None:
        auth_data = await self._taiga_client.login(email, password)

        taiga_session = TaigaSession(
            chat_id=chat_id,
            telegram_username=telegram_username,
            access_token_encrypted=self._cipher.encrypt(auth_data["auth_token"]),
            refresh_token_encrypted=self._cipher.encrypt(auth_data["refresh"]),
        )
        await session.merge(taiga_session)
        await session.commit()

    async def logout(self, session: AsyncSession, chat_id: int) -> bool:
        taiga_session = await session.get(TaigaSession, chat_id)

        if taiga_session is None:
            return False

        await session.delete(taiga_session)
        await session.commit()
        return True

    async def list_my_projects(self, session: AsyncSession, chat_id: int) -> list[str]:
        async def fetch(access_token: str) -> list[str]:
            user = await self._taiga_client.me(access_token)
            projects = await self._taiga_client.list_projects(access_token, user["id"])
            return [project["name"] for project in projects]

        return await self._call_with_valid_token(session, chat_id, fetch)

    async def list_pending_user_stories(self, session: AsyncSession, chat_id: int) -> list[str]:
        async def fetch(access_token: str) -> list[str]:
            user = await self._taiga_client.me(access_token)
            user_stories = await self._taiga_client.list_user_stories(access_token, user["id"])
            return [story["subject"] for story in user_stories if not story["is_closed"]]

        return await self._call_with_valid_token(session, chat_id, fetch)

    async def _call_with_valid_token(
        self,
        session: AsyncSession,
        chat_id: int,
        call: Callable[[str], Awaitable[T]],
    ) -> T:
        taiga_session = await session.get(TaigaSession, chat_id)

        if taiga_session is None:
            raise NotLoggedInError()

        access_token = self._cipher.decrypt(taiga_session.access_token_encrypted)

        try:
            return await call(access_token)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 401:
                raise

            # The access_token expired: use the stored refresh_token to get a new
            # pair, persist it, and retry the call exactly once.
            access_token = await self._refresh(session, taiga_session)
            return await call(access_token)

    async def _refresh(self, session: AsyncSession, taiga_session: TaigaSession) -> str:
        refresh_token = self._cipher.decrypt(taiga_session.refresh_token_encrypted)
        auth_data = await self._taiga_client.refresh_token(refresh_token)

        taiga_session.access_token_encrypted = self._cipher.encrypt(auth_data["auth_token"])
        taiga_session.refresh_token_encrypted = self._cipher.encrypt(auth_data["refresh"])
        session.add(taiga_session)
        await session.commit()

        return auth_data["auth_token"]


def get_taiga_auth_service(
    taiga_client: TaigaClient = Depends(get_taiga_client),
    cipher: TokenCipher = Depends(get_token_cipher),
) -> TaigaAuthService:
    return TaigaAuthService(taiga_client, cipher)
