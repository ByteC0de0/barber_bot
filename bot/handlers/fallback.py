"""Сюда попадает всё, что не обработали другие роутеры. Подключается последним."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.keyboards.client import main_menu

router = Router()


@router.message()
async def unknown_message(message: Message, config: Config) -> None:
    await message.answer(
        "Не понял 🙂 Воспользуйтесь кнопками меню ниже.",
        reply_markup=main_menu(config.is_admin(message.from_user.id)),
    )


@router.callback_query()
async def unknown_callback(callback: CallbackQuery) -> None:
    await callback.answer("Эта кнопка устарела. Откройте меню заново: /start", show_alert=True)
