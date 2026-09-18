from datetime import datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel


class TelegramMessageLog(SQLModel, table=True):
    """Every message the bot has sent to or received from a chat, so a
    logout can find and delete all of them — Telegram has no endpoint to
    list a chat's past messages, so this is the only way to know what's
    there."""

    __tablename__ = "telegram_message_log"

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    message_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TelegramMenuAnchor(SQLModel, table=True):
    """Tracks the most recent root-menu message sent to a chat, so pushed
    notifications (webhook events, due-date reminders) can re-send it at
    the bottom of the chat instead of leaving it buried above them."""

    __tablename__ = "telegram_menu_anchor"

    chat_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    message_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
