from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_taiga_bot.telegram.client import get_telegram_client
from fastapi_taiga_bot.telegram.router import router as telegram_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_telegram_client().close()

app = FastAPI(lifespan=lifespan)
app.include_router(telegram_router)