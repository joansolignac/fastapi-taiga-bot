# fastapi-taiga-bot

A Telegram bot, built on FastAPI, that lets each user log into their own Taiga account and check their projects and pending user stories directly from a chat menu.

## Features

- Telegram integration implemented from scratch on top of `httpx` (webhook-based, no bot framework).
- Per-user Taiga login (`/login`) with credentials encrypted at rest in Postgres — no shared/technical Taiga account.
- Inline-keyboard menu (`/start`), gated by login state:
  - Not logged in → only a "🔐 Iniciar sesión" button.
  - Logged in → 🗂️ Proyectos, 📌 Pendientes, ❓ Ayuda, 🔓 Cerrar sesión.
- Slash-command equivalents for every menu option (`/login`, `/logout`, `/projects`, `/pendings`).
- Automatic access-token refresh against Taiga's API when it expires.

## Requirements

- Python >=3.14
- [uv](https://docs.astral.sh/uv/) as package manager
- Docker (for local Postgres via `docker compose`)
- A tunnel (e.g. [ngrok](https://ngrok.com/)) to expose your local server with HTTPS for Telegram's webhook

## Setup

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Copy `.env` and fill in the required variables (see below).
3. Start Postgres locally:
   ```bash
   docker compose up -d
   ```
4. Apply database migrations:
   ```bash
   uv run alembic upgrade head
   ```
5. Run the server:
   ```bash
   uv run fastapi dev src/fastapi_taiga_bot/main.py
   ```
6. Expose it with a tunnel and register the Telegram webhook (see `CLAUDE.md` for the exact `curl` command).

## Environment variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather). |
| `TELEGRAM_WEBHOOK_SECRET` | Random secret; validated against Telegram's `X-Telegram-Bot-Api-Secret-Token` header on every webhook call. |
| `TAIGA_BASE_URL` | Base URL of your Taiga instance's REST API, e.g. `https://taiga.example.com/api/v1`. |
| `DATABASE_URL` | Postgres connection string using the async driver, e.g. `postgresql+asyncpg://user:pass@localhost:5433/db`. |
| `TAIGA_TOKEN_ENCRYPTION_KEY` | A Fernet key used to encrypt/decrypt stored Taiga access/refresh tokens. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |

## Bot commands

| Command | Description |
|---|---|
| `/start` | Shows the main menu (login-gated). |
| `/login <email> <password>` | Logs into Taiga; the message with the password is deleted immediately after processing. |
| `/logout` | Clears the stored Taiga session. |
| `/projects` | Lists the names of your Taiga projects. |
| `/pendings` | Lists your open (non-closed) Taiga user stories. |

## Development

See [CLAUDE.md](CLAUDE.md) for the full architecture reference (module layout, dependency-injection conventions, database/migrations workflow, and local webhook testing).

There are no automated tests, linter, or formatter configured yet.
