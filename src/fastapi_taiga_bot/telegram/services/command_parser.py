from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate


def parser_command(update: TelegramUpdate) -> tuple[str, str] | None:
    if not update.is_command:
        return None

    text = update.message.text.strip()
    parts = text.split(maxsplit=1)

    command_name = parts[0][1:].split("@")[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    return command_name, args
