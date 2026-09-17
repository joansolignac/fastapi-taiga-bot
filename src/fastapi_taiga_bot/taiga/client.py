from functools import lru_cache

import httpx

from fastapi_taiga_bot.config import Settings, get_settings

class TaigaClient:
    def __init__(self):
        settings = get_settings()
        self._base_url = settings.taiga_base_url
        self._client =  httpx.AsyncClient(base_url=self._base_url)
    
    async def login(self, email: str, password: str) -> dict:
        response = await self._client.post(
            url="/auth",
            json={
                "type": "normal",
                "username": email,
                "password": password
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def refresh_token(self, refresh_token: str) -> dict:
        response = await self._client.post(
            url="/auth/refresh",
            json={
                "refresh": refresh_token
            }
        )
        response.raise_for_status()
        return response.json()

    async def me(self, access_token: str) -> dict:
        response = await self._client.get(
            url="/users/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def list_projects(self, access_token: str, member_id: int) -> list[dict]:
        response = await self._client.get(
            url="/projects",
            params={"member": member_id},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def list_user_stories(self, access_token: str, assigned_users: int) -> list[dict]:
        response = await self._client.get(
            url="/userstories",
            params={"assigned_users": assigned_users, "status__is_closed": "false"},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def list_all_open_user_stories(self, access_token: str) -> list[dict]:
        response = await self._client.get(
            url="/userstories",
            params={"status__is_closed": "false"},
            headers={
                "Authorization": f"Bearer {access_token}",
                # Taiga paginates at 30 items by default; the due-date scan needs
                # every open story across every project in a single pass.
                "x-disable-pagination": "True",
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_user_story(self, access_token: str, story_id: int) -> dict:
        response = await self._client.get(
            url=f"/userstories/{story_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def add_comment(
        self, access_token: str, story_id: int, version: int, comment: str
    ) -> dict:
        response = await self._client.patch(
            url=f"/userstories/{story_id}",
            json={"comment": comment, "version": version},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()
        

@lru_cache
def get_taiga_client() -> TaigaClient:
    return TaigaClient()
