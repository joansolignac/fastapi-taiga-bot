from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_taiga_bot.telegram.client import get_telegram_client
from fastapi_taiga_bot.telegram.router import router as telegram_router

from fastapi_taiga_bot.taiga.client import get_taiga_client
from fastapi_taiga_bot.taiga.router import router as taiga_router
from fastapi_taiga_bot.db.engine import get_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_telegram_client().close()
    await get_taiga_client().close()
    await get_engine().dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(telegram_router)
app.include_router(taiga_router)