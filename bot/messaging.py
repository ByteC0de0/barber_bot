"""Отправка и редактирование сообщений с обработкой типичных ошибок Telegram."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Config

logger = logging.getLogger(__name__)


async def send_safe(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """Отправляет сообщение; если не вышло (пользователь заблокировал бота и т.п.) — пишет в лог."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramAPIError as e:
        logger.warning("Не удалось отправить сообщение в чат %s: %s", chat_id, e)
        return False


async def notify_admins(bot: Bot, config: Config, text: str) -> None:
    for admin_id in config.admin_ids:
        await send_safe(bot, admin_id, text)


async def edit_message(
    callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Меняет сообщение, на кнопку которого нажали. Если оно слишком старое — шлёт новое."""
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
            logger.info("Не удалось изменить сообщение, отправляю новое: %s", e)
    await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
