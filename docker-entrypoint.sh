#!/bin/sh
set -e

alembic upgrade head

exec fastapi run src/fastapi_taiga_bot/main.py --host 0.0.0.0 --port "${PORT:-8000}"
