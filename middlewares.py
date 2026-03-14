from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from config import ADMIN_IDS
from database import get_bot_state

class BotActiveMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if event.from_user.id in ADMIN_IDS:
            return await handler(event, data)
        if not get_bot_state():
            return
        return await handler(event, data)

class CallbackActiveMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        if event.from_user.id in ADMIN_IDS:
            return await handler(event, data)
        if not get_bot_state():
            await event.answer("Бот временно недоступен", show_alert=True)
            return
        return await handler(event, data)