"""Данные inline-кнопок (callback_data, до 64 байт).

Это Pydantic-модели: при нажатии aiogram разбирает строку кнопки и проверяет
поля. Битые или подделанные данные не пройдут фильтр, и такое нажатие
обработает fallback («кнопка устарела»).

Разделитель внутри callback_data — «:», поэтому время пишем без двоеточия:
день — ГГГГММДД, дата и время — ГГГГММДДЧЧММ.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from aiogram.filters.callback_data import CallbackData
from pydantic import AfterValidator, Field

DAY_FORMAT = "%Y%m%d"
DT_FORMAT = "%Y%m%d%H%M"

# Простые кнопки без параметров
BOOK_SERVICES = "book:services"
BOOK_ABORT = "book:abort"


def _check_format(fmt: str, allow_empty: bool = False):
    def check(value: str) -> str:
        if allow_empty and value == "":
            return value
        datetime.strptime(value, fmt)  # ValueError, если строка не дата
        return value

    return AfterValidator(check)


DayStr = Annotated[str, Field(pattern=r"^\d{8}$"), _check_format(DAY_FORMAT)]
DateTimeStr = Annotated[str, Field(pattern=r"^\d{12}$"), _check_format(DT_FORMAT)]
OptionalDayStr = Annotated[
    str, Field(pattern=r"^(\d{8})?$"), _check_format(DAY_FORMAT, allow_empty=True)
]
OptionalDateTimeStr = Annotated[
    str, Field(pattern=r"^(\d{12})?$"), _check_format(DT_FORMAT, allow_empty=True)
]
Id = Annotated[int, Field(ge=0)]


def pack_day(d: date) -> str:
    return d.strftime(DAY_FORMAT)


def unpack_day(value: str) -> date:
    return datetime.strptime(value, DAY_FORMAT).date()


def pack_dt(dt: datetime) -> str:
    return dt.strftime(DT_FORMAT)


def unpack_dt(value: str) -> datetime:
    return datetime.strptime(value, DT_FORMAT)


class ServiceCb(CallbackData, prefix="svc"):
    service_id: Id


class DayCb(CallbackData, prefix="day"):
    service_id: Id
    day: DayStr

    @property
    def day_date(self) -> date:
        return unpack_day(self.day)


class SlotCb(CallbackData, prefix="slot"):
    service_id: Id
    at: DateTimeStr

    @property
    def start(self) -> datetime:
        return unpack_dt(self.at)


class ConfirmCb(CallbackData, prefix="ok"):
    service_id: Id
    at: DateTimeStr

    @property
    def start(self) -> datetime:
        return unpack_dt(self.at)


class MyCb(CallbackData, prefix="my"):
    action: Literal["ask", "cancel", "keep"]
    booking_id: Id


AdminAction = Literal[
    "menu", "today", "pick_day", "day", "cancel_ask", "cancel",
    "block_pick", "block_day", "block_from", "block_to", "block_full",
    "blocks", "unblock",
]


class AdminCb(CallbackData, prefix="adm"):
    action: AdminAction
    day: OptionalDayStr = ""
    start: OptionalDateTimeStr = ""
    end: OptionalDateTimeStr = ""
    item_id: Id = 0

    @property
    def day_date(self) -> date:
        return unpack_day(self.day)

    @property
    def start_dt(self) -> datetime:
        return unpack_dt(self.start)

    @property
    def end_dt(self) -> datetime:
        return unpack_dt(self.end)
