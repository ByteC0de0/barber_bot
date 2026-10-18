"""Данные inline-кнопок (callback_data, до 64 байт).

Разделитель внутри callback_data — «:», поэтому время пишем без двоеточия:
день — ГГГГММДД, дата и время — ГГГГММДДЧЧММ.
"""

from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData

# Простые кнопки без параметров
BOOK_SERVICES = "book:services"
BOOK_ABORT = "book:abort"


class ServiceCb(CallbackData, prefix="svc"):
    service_id: int


class DayCb(CallbackData, prefix="day"):
    service_id: int
    day: str


class SlotCb(CallbackData, prefix="slot"):
    service_id: int
    at: str


class ConfirmCb(CallbackData, prefix="ok"):
    service_id: int
    at: str


class MyCb(CallbackData, prefix="my"):
    action: str  # ask | cancel | keep
    booking_id: int


class AdminCb(CallbackData, prefix="adm"):
    action: str
    day: str = ""
    start: str = ""
    end: str = ""
    item_id: int = 0


def pack_day(d: date) -> str:
    return d.strftime("%Y%m%d")


def unpack_day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def pack_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def unpack_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M")
