import logging

from fastapi import Depends

from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.callbacks.auth_login import AuthLoginCallback, get_auth_login_callback
from fastapi_taiga_bot.telegram.callbacks.auth_logout import AuthLogoutCallback, get_auth_logout_callback
from fastapi_taiga_bot.telegram.callbacks.menu_help import MenuHelpCallback, get_menu_help_callback
from fastapi_taiga_bot.telegram.callbacks.menu_pendings import MenuPendingsCallback, get_menu_pendings_callback
from fastapi_taiga_bot.telegram.callbacks.menu_projects import MenuProjectsCallback, get_menu_projects_callback
from fastapi_taiga_bot.telegram.callbacks.menu_root import MenuRootCallback, get_menu_root_callback
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate

logger = logging.getLogger()


class CallbackDispatcher:
    def __init__(self, telegram_client: TelegramClient):
        self._callbacks: dict[str, TelegramCallback] = {}
        self._client = telegram_client

    def register(self, callback: TelegramCallback) -> None:
        if callback.data in self._callbacks:
            raise ValueError(f"Duplicate callback: {callback.data}")
        self._callbacks[callback.data] = callback

    async def dispatch(self, update: TelegramUpdate) -> None:
        callback_query = update.callback_query
        callback = self._callbacks.get(callback_query.data)

        try:
            if callback is None:
                logger.info(f"Unknown callback: {callback_query.data}")
            else:
                await callback.handle(update)
        except Exception:
            logger.exception(f"Failed callback: {callback_query.data}")
        finally:
            await self._client.answer_callback_query(callback_query.id)


def get_callback_dispatcher(
    telegram_client: TelegramClient = Depends(get_telegram_client),
    menu_root: MenuRootCallback = Depends(get_menu_root_callback),
    auth_login: AuthLoginCallback = Depends(get_auth_login_callback),
    auth_logout: AuthLogoutCallback = Depends(get_auth_logout_callback),
    menu_projects: MenuProjectsCallback = Depends(get_menu_projects_callback),
    menu_pendings: MenuPendingsCallback = Depends(get_menu_pendings_callback),
    menu_help: MenuHelpCallback = Depends(get_menu_help_callback),
    ) -> CallbackDispatcher:
    dispatcher = CallbackDispatcher(telegram_client)
    dispatcher.register(menu_root)
    dispatcher.register(auth_login)
    dispatcher.register(auth_logout)
    dispatcher.register(menu_projects)
    dispatcher.register(menu_pendings)
    dispatcher.register(menu_help)
    return dispatcher
