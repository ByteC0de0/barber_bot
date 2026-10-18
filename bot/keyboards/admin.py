"""Клавиатуры админ-панели."""

from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import formatting as fmt
from bot.callbacks import AdminCb, pack_day, pack_dt
from bot.database import Block, Booking


def _button(text: str, **cb: str | int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=AdminCb(**cb).pack())


def menu_button() -> InlineKeyboardButton:
    return _button("◀️ В меню", action="menu")


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("📋 Записи на сегодня", action="today")],
            [_button("📆 Записи на другой день", action="pick_day")],
            [_button("⛔ Закрыть время", action="block_pick")],
            [_button("✅ Открыть закрытое время", action="blocks")],
        ]
    )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])


def days_kb(days: list[date], action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in days:
        builder.button(text=fmt.day_short(day), callback_data=AdminCb(action=action, day=pack_day(day)))
    builder.adjust(3)
    builder.row(menu_button())
    return builder.as_markup()


def day_kb(day: date, cancellable: list[Booking]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for booking in cancellable:
        builder.button(
            text=f"❌ {fmt.hm(booking.start)} {booking.client_name}",
            callback_data=AdminCb(action="cancel_ask", item_id=booking.id),
        )
    builder.adjust(1)
    builder.row(_button("🔄 Обновить", action="day", day=pack_day(day)))
    builder.row(_button("📆 Другой день", action="pick_day"), menu_button())
    return builder.as_markup()


def cancel_confirm_kb(booking: Booking) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Да, отменить", action="cancel", item_id=booking.id),
                _button("Нет", action="day", day=pack_day(booking.start.date())),
            ]
        ]
    )


def block_start_kb(day: date, starts: list[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🌙 Весь день (выходной)",
        callback_data=AdminCb(action="block_full", day=pack_day(day)),
    )
    for start in starts:
        builder.button(text=fmt.hm(start), callback_data=AdminCb(action="block_from", start=pack_dt(start)))
    builder.adjust(1, 4)
    builder.row(_button("◀️ Другой день", action="block_pick"), menu_button())
    return builder.as_markup()


def block_end_kb(start: datetime, ends: list[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for end in ends:
        builder.button(
            text=fmt.hm(end),
            callback_data=AdminCb(action="block_to", start=pack_dt(start), end=pack_dt(end)),
        )
    builder.adjust(4)
    builder.row(
        _button("◀️ Назад", action="block_day", day=pack_day(start.date())),
        menu_button(),
    )
    return builder.as_markup()


def block_conflict_kb(day: date) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("📋 Записи на этот день", action="day", day=pack_day(day))],
            [menu_button()],
        ]
    )


def blocks_kb(blocks: list[Block]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for block in blocks:
        builder.button(
            text=f"✅ {fmt.block_line(block)}",
            callback_data=AdminCb(action="unblock", item_id=block.id),
        )
    builder.adjust(1)
    builder.row(menu_button())
    return builder.as_markup()
