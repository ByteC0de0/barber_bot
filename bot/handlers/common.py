"""Общие команды: /start, /id, прайс."""

import logging

from aiogram import F, Router, html
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot import formatting as fmt
from bot.config import Config
from bot.database import Database
from bot.keyboards.client import BTN_PRICES, book_button, main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    user = message.from_user
    logger.info("/start от %s (id=%s)", user.full_name, user.id)
    await message.answer(
        f"Привет, {html.bold(html.quote(user.full_name))}! 👋\n\n"
        f"Это бот записи в {html.quote(config.salon_name)}.\n"
        "Выберите услугу, удобные дату и время — а я напомню о визите заранее.",
        reply_markup=main_menu(config.is_admin(user.id)),
    )


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: {html.code(str(message.from_user.id))}")


@router.message(Command("prices"))
@router.message(F.text == BTN_PRICES)
async def show_prices(message: Message, db: Database) -> None:
    services = await db.get_services()
    lines = [
        f"• {html.quote(s.name)} — {html.bold(fmt.price(s.price))}, {fmt.duration(s.duration)}"
        for s in services
    ]
    await message.answer(
        "💈 " + html.bold("Услуги и цены") + "\n\n" + "\n".join(lines),
        reply_markup=book_button(),
    )
