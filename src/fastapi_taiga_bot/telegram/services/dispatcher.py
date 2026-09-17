import logging

from fastapi import Depends
from fastapi_taiga_bot.telegram.commands.base import TelegramCommand
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.command_parser import parser_command
from fastapi_taiga_bot.telegram.commands.start import StartCommand, get_start_command
from fastapi_taiga_bot.telegram.commands.login import LoginCommand, get_login_command
from fastapi_taiga_bot.telegram.commands.logout import LogoutCommand, get_logout_command
from fastapi_taiga_bot.telegram.commands.projects import ProjectsCommand, get_projects_command
from fastapi_taiga_bot.telegram.commands.pendings import PendingsCommand, get_pendings_command
from fastapi_taiga_bot.telegram.services.conversation_state import (
    ConversationStateService,
    get_conversation_state,
)

logger = logging.getLogger()


class CommandDispatcher:
    def __init__(self, login_command: LoginCommand, conversation_state: ConversationStateService):
        self._commands: dict[str, TelegramCommand] = {}
        self._login_command = login_command
        self._conversation_state = conversation_state

    def register(self, command: TelegramCommand) -> None:
        if command.name in self._commands:
            raise ValueError(f"Duplicate command: {command.name}")
        self._commands[command.name] = command

    def get_commands(self) -> list[TelegramCommand]:
        return list(self._commands.values())

    async def dispatch(self, update: TelegramUpdate) -> None:
        if (
            update.message is not None
            and not update.is_command
            and self._conversation_state.consume_awaiting_login(update.message.chat.id)
        ):
            try:
                await self._login_command.handle(update, update.message.text or "")
            except Exception:
                logger.exception("Failed command: login")
            return

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
    start_command: StartCommand = Depends(get_start_command),
    login_command: LoginCommand = Depends(get_login_command),
    logout_command: LogoutCommand = Depends(get_logout_command),
    projects_command: ProjectsCommand = Depends(get_projects_command),
    pendings_command: PendingsCommand = Depends(get_pendings_command),
    conversation_state: ConversationStateService = Depends(get_conversation_state),
    ) -> CommandDispatcher:
    dispatcher = CommandDispatcher(login_command, conversation_state)
    dispatcher.register(start_command)
    dispatcher.register(login_command)
    dispatcher.register(logout_command)
    dispatcher.register(projects_command)
    dispatcher.register(pendings_command)
    return dispatcher
