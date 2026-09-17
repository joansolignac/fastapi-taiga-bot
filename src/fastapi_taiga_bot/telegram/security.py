import secrets

from fastapi import Depends, Header, HTTPException, status

from fastapi_taiga_bot.config import Settings, get_settings


async def verify_telegram_webhook_secret(
    x_telegram_bot_api_secret_token: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if not secrets.compare_digest(
        x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid secret token")
