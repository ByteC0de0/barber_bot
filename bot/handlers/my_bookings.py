"""Мои записи: просмотр и отмена клиентом."""

from aiogram import Bot, F, Router, html
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import formatting as fmt
from bot.callbacks import MyCb
from bot.config import Config
from bot.database import Booking, Database
from bot.keyboards.client import BTN_MY, cancel_confirm_kb, my_bookings_kb
from bot.messaging import edit_message, notify_admins

router = Router()


async def _render_list(
    user_id: int, db: Database, config: Config
) -> tuple[str, InlineKeyboardMarkup | None]:
    bookings = await db.get_user_upcoming(user_id, config.now())
    if not bookings:
        return (
            "У вас нет предстоящих записей.\n"
            "Нажмите «📅 Записаться», чтобы выбрать время.",
            None,
        )
    cards = "\n\n".join(fmt.booking_details(b) for b in bookings)
    return f"📋 {html.bold('Ваши записи')}\n\n{cards}", my_bookings_kb(bookings)


async def _own_upcoming(
    callback: CallbackQuery, booking_id: int, db: Database, config: Config
) -> Booking | None:
    """Запись, если она принадлежит этому клиенту, активна и ещё не началась."""
    booking = await db.get_booking(booking_id)
    if (
        booking is None
        or booking.user_id != callback.from_user.id
        or booking.status != "active"
        or booking.start <= config.now()
    ):
        return None
    return booking


@router.message(Command("my"))
@router.message(F.text == BTN_MY)
async def my_bookings(message: Message, db: Database, config: Config) -> None:
    text, keyboard = await _render_list(message.from_user.id, db, config)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(MyCb.filter(F.action == "ask"))
async def ask_cancel(
    callback: CallbackQuery, callback_data: MyCb, db: Database, config: Config
) -> None:
    booking = await _own_upcoming(callback, callback_data.booking_id, db, config)
    if booking is None:
        await callback.answer("Эта запись уже отменена или прошла", show_alert=True)
        return
    await edit_message(
        callback,
        f"Отменить запись?\n\n{fmt.booking_details(booking)}",
        cancel_confirm_kb(booking.id),
    )
    await callback.answer()


@router.callback_query(MyCb.filter(F.action == "cancel"))
async def do_cancel(
    callback: CallbackQuery, callback_data: MyCb, db: Database, config: Config, bot: Bot
) -> None:
    booking = await _own_upcoming(callback, callback_data.booking_id, db, config)
    if booking is None or not await db.cancel_booking(booking.id, by="client"):
        await callback.answer("Эта запись уже отменена или прошла", show_alert=True)
        text, keyboard = await _render_list(callback.from_user.id, db, config)
        await edit_message(callback, text, keyboard)
        return

    await edit_message(callback, f"❌ Запись отменена.\n\n{fmt.booking_details(booking)}")
    await callback.answer("Запись отменена")
    await notify_admins(
        bot,
        config,
        f"❌ {html.bold('Клиент отменил запись')}\n\n"
        f"{fmt.booking_details(booking)}\n👤 {fmt.client_mention(booking)}",
    )


@router.callback_query(MyCb.filter(F.action == "keep"))
async def keep_booking(callback: CallbackQuery, db: Database, config: Config) -> None:
    text, keyboard = await _render_list(callback.from_user.id, db, config)
    await edit_message(callback, text, keyboard)
    await callback.answer("Запись сохранена 👍")
