import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.telegram.client import get_telegram_client
from fastapi_taiga_bot.telegram.router import router as telegram_router

from fastapi_taiga_bot.taiga.client import get_taiga_client
from fastapi_taiga_bot.taiga.router import router as taiga_router
from fastapi_taiga_bot.taiga.services.due_date_reminder_service import (
    get_taiga_due_date_reminder_service,
)
from fastapi_taiga_bot.db.engine import get_engine

logger = logging.getLogger()


async def run_due_date_check() -> None:
    session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await get_taiga_due_date_reminder_service().check_due_dates(session)
    except Exception:
        # A failing run must not take the scheduler down with it.
        logger.exception("Failed due date check")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_due_date_check, CronTrigger(hour=8, minute=0))
    scheduler.start()

    yield

    scheduler.shutdown()
    await get_telegram_client().close()
    await get_taiga_client().close()
    await get_engine().dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(telegram_router)
app.include_router(taiga_router)
