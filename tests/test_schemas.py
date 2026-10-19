from datetime import date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from bot.callbacks import AdminCb, DayCb, MyCb, SlotCb
from bot.database import Service
from bot.schemas import BlockRequest, BookingRequest, first_error

NOW = datetime(2030, 1, 15, 9, 0)
DAY = date(2030, 1, 16)
HAIRCUT = Service(id=1, name="Мужская стрижка", price=1500, duration=60)


def at(h, m=0, day=DAY):
    return datetime.combine(day, time(h, m))


def booking(config, start, free=None, **fields):
    data = {"service": HAIRCUT, "start": start, "user_id": 1, "client_name": "Иван", **fields}
    context = {"config": config, "now": NOW, "free_slots": [start] if free is None else free}
    return BookingRequest.model_validate(data, context=context)


def booking_error(config, start, **kwargs) -> str:
    with pytest.raises(ValidationError) as e:
        booking(config, start, **kwargs)
    return first_error(e.value)


def test_valid_booking(config):
    request = booking(config, at(10), client_name="  Иван  ")
    assert request.client_name == "Иван"
    assert request.end == at(11)


@pytest.mark.parametrize(
    ("start", "message"),
    [
        (NOW - timedelta(hours=1), "уже прошло"),
        (at(10, day=DAY + timedelta(days=30)), "дней вперёд"),
        (at(8), "Салон работает"),
        (at(19, 30), "Салон работает"),  # 60 минут не влезают до 20:00
        (at(10, 15), "Выберите время из списка"),
    ],
)
def test_time_rules(config, start, message):
    assert message in booking_error(config, start)


def test_busy_time_rejected(config):
    assert "уже занято" in booking_error(config, at(12), free=[at(10), at(11)])


@pytest.mark.parametrize("fields", [{"client_name": "   "}, {"user_id": 0}])
def test_client_data_required(config, fields):
    with pytest.raises(ValidationError):
        booking(config, at(10), **fields)


def test_context_is_required():
    with pytest.raises(RuntimeError):
        BookingRequest.model_validate(
            {"service": HAIRCUT, "start": at(10), "user_id": 1, "client_name": "Иван"}
        )


def block(config, start, end, reason="Перерыв"):
    return BlockRequest.model_validate(
        {"start": start, "end": end, "reason": reason},
        context={"config": config, "now": NOW},
    )


def test_valid_blocks(config):
    assert block(config, at(14), at(15)).start == at(14)
    full = block(config, datetime.combine(DAY, time.min), datetime.combine(DAY + timedelta(days=1), time.min))
    assert full.is_full_day


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (at(15), at(14), "позже начала"),
        (at(8, day=date(2030, 1, 14)), at(9, day=date(2030, 1, 14)), "уже прошло"),
        (at(14, 10), at(15), "по сетке"),
        (at(19), at(21), "по сетке"),
    ],
)
def test_invalid_blocks(config, start, end, message):
    with pytest.raises(ValidationError) as e:
        block(config, start, end)
    assert message in first_error(e.value)


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (DayCb, "day:1:2030-01-16"),
        (DayCb, "day:1:20301399"),
        (SlotCb, "slot:1:2030011610"),
        (SlotCb, "slot:-5:203001161000"),
        (MyCb, "my:delete_all:1"),
        (AdminCb, "adm:drop_table::::0"),
        (AdminCb, "adm:block_to::2030011614:20300116:0"),
    ],
)
def test_broken_callback_data_rejected(model, data):
    with pytest.raises(ValueError):
        model.unpack(data)


def test_callback_data_roundtrip():
    cb = SlotCb.unpack(SlotCb(service_id=2, at="203001161030").pack())
    assert cb.start == at(10, 30)
    assert AdminCb.unpack("adm:day:20300116:::0").day_date == DAY
