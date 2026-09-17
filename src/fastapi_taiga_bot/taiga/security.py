import hashlib
import hmac

from fastapi import Depends, HTTPException, Request, status

from fastapi_taiga_bot.config import Settings, get_settings


async def verify_taiga_webhook_secret(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    received = request.headers.get("X-Taiga-Webhook-Signature")
    body = await request.body()

    if not received:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing signature")

    expected = hmac.new(
        settings.taiga_webhook_secret.encode(), body, hashlib.sha1
    ).hexdigest()

    if not hmac.compare_digest(received, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")
