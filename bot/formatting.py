"""Форматирование дат, цен и карточек записей для сообщений."""

from datetime import date, datetime, timedelta

from aiogram import html

from bot.database import Block, Booking, Service

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
WEEKDAYS_FULL = (
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
)
MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def day_short(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d:%d.%m}"


def day_long(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}, {WEEKDAYS_FULL[d.weekday()]}"


def relative_day(d: date, today: date) -> str:
    if d == today:
        return "сегодня"
    if d == today + timedelta(days=1):
        return "завтра"
    return day_long(d)


def hm(dt: datetime) -> str:
    return f"{dt:%H:%M}"


def price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if mins:
        parts.append(f"{mins} мин")
    return " ".join(parts)


def service_line(service: Service) -> str:
    return f"{service.name} · {price(service.price)} · {duration(service.duration)}"


def booking_details(booking: Booking) -> str:
    return (
        f"💈 {html.bold(html.quote(booking.service_name))}\n"
        f"📅 {day_long(booking.start.date())}\n"
        f"🕐 {hm(booking.start)}–{hm(booking.end)}\n"
        f"💰 {price(booking.price)}"
    )


def client_mention(booking: Booking) -> str:
    text = html.link(html.quote(booking.client_name), f"tg://user?id={booking.user_id}")
    if booking.client_username:
        text += f" (@{booking.client_username})"
    return text


def block_line(block: Block) -> str:
    if block.is_full_day:
        return f"{day_short(block.start.date())} · весь день · {html.quote(block.reason)}"
    return (
        f"{day_short(block.start.date())} · {hm(block.start)}–{hm(block.end)}"
        f" · {html.quote(block.reason)}"
    )
