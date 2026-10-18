"""Клавиатуры для клиентов."""

from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot import formatting as fmt
from bot.callbacks import (
    BOOK_ABORT,
    BOOK_SERVICES,
    ConfirmCb,
    DayCb,
    MyCb,
    ServiceCb,
    SlotCb,
    pack_day,
    pack_dt,
)
from bot.database import Booking, Service

BTN_BOOK = "📅 Записаться"
BTN_MY = "📋 Мои записи"
BTN_PRICES = "💈 Услуги и цены"
BTN_ADMIN = "🛠 Админ-панель"


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_BOOK)
    builder.button(text=BTN_MY)
    builder.button(text=BTN_PRICES)
    if is_admin:
        builder.button(text=BTN_ADMIN)
    builder.adjust(1, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def book_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_BOOK, callback_data=BOOK_SERVICES)]]
    )


def services_kb(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.button(text=fmt.service_line(service), callback_data=ServiceCb(service_id=service.id))
    builder.adjust(1)
    return builder.as_markup()


def back_to_services_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ К услугам", callback_data=BOOK_SERVICES)]]
    )


def days_kb(service_id: int, days: list[date]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in days:
        builder.button(
            text=fmt.day_short(day),
            callback_data=DayCb(service_id=service_id, day=pack_day(day)),
        )
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="◀️ К услугам", callback_data=BOOK_SERVICES))
    return builder.as_markup()


def slots_kb(service_id: int, slots: list[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in slots:
        builder.button(
            text=fmt.hm(slot),
            callback_data=SlotCb(service_id=service_id, at=pack_dt(slot)),
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(
            text="◀️ К датам",
            callback_data=ServiceCb(service_id=service_id).pack(),
        )
    )
    return builder.as_markup()


def confirm_kb(service_id: int, start: datetime) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить запись",
        callback_data=ConfirmCb(service_id=service_id, at=pack_dt(start)),
    )
    builder.button(
        text="◀️ Другое время",
        callback_data=DayCb(service_id=service_id, day=pack_day(start.date())),
    )
    builder.button(text="✖️ Отмена", callback_data=BOOK_ABORT)
    builder.adjust(1, 2)
    return builder.as_markup()


def my_bookings_kb(bookings: list[Booking]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"❌ Отменить: {fmt.day_short(booking.start.date())} {fmt.hm(booking.start)}",
            callback_data=MyCb(action="ask", booking_id=booking.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, отменить", callback_data=MyCb(action="cancel", booking_id=booking_id))
    builder.button(text="Нет, оставить", callback_data=MyCb(action="keep", booking_id=booking_id))
    builder.adjust(2)
    return builder.as_markup()


def reminder_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить запись", callback_data=MyCb(action="ask", booking_id=booking_id))
    return builder.as_markup()
