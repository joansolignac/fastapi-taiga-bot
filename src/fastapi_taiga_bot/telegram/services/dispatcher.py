import logging

from fastapi import Depends
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.command_parser import parser_command
from fastapi_taiga_bot.telegram.commands.start import StartCommand, get_start_command

logger = logging.getLogger()


class CommandDispatcher:
    def __init__(self):
        self._commands: dict[str, TelegramCommand] = {}

    def register(self, command: TelegramCommand) -> None:
        if command.name in self._commands:
            raise ValueError(f"Duplicate command: {command.name}")
        self._commands[command.name] = command

    async def dispatch(self, update: TelegramUpdate) -> None:
        parsed = parser_command(update)

        if parsed is None:
            return

        command_name, args = parsed
        command = self._commands.get(command_name)

        if command is None:
            logger.info(f"Unknow command: {command_name}")
            return

        try:
            await command.handle(update, args)
        except Exception:
            logger.exception(f"Failed command: {command.name}")


def get_dispatcher(
    start_command: StartCommand = Depends(get_start_command)
    ) -> CommandDispatcher:
    dispatcher = CommandDispatcher()
    dispatcher.register(start_command)
    return dispatcher
