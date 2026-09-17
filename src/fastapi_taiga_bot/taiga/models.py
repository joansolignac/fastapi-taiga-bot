from datetime import datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel


class TaigaSession(SQLModel, table=True):
    __tablename__ = "taiga_session"

    # Telegram chat_ids can exceed the range of a 32-bit INTEGER,
    # so they're mapped to BIGINT explicitly instead of SQLModel's default.
    chat_id: int = Field(sa_column=Column(BigInteger, primary_key=True, autoincrement=False))
    telegram_username: str | None = None
    access_token_encrypted: str
    refresh_token_encrypted: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
