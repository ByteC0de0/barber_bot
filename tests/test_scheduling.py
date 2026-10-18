from datetime import date, datetime, time, timedelta

from bot.formatting import hm
from bot.scheduling import day_slots, time_grid

DAY = date(2030, 1, 15)
LONG_AGO = datetime(2030, 1, 1)


def slots(duration, busy=(), now=LONG_AGO):
    found = day_slots(
        DAY, duration, list(busy), now, work_start=time(10), work_end=time(20), step=30
    )
    return [hm(s) for s in found]


def at(h, m=0):
    return datetime.combine(DAY, time(h, m))


def test_service_must_finish_before_closing():
    assert slots(60)[0] == "10:00"
    assert slots(60)[-1] == "19:00"
    assert slots(90)[-1] == "18:30"
    assert slots(45)[-1] == "19:00"


def test_past_and_current_time_hidden():
    assert slots(30, now=at(13, 10))[0] == "13:30"
    assert slots(30, now=at(13, 30))[0] == "14:00"
    assert slots(30, now=at(20)) == []


def test_busy_interval_blocks_overlapping_slots():
    result = slots(60, busy=[(at(12), at(13))])
    assert "11:00" in result  # заканчивается ровно в 12:00 — можно
    assert "11:30" not in result
    assert "12:00" not in result
    assert "12:30" not in result
    assert "13:00" in result


def test_full_day_block():
    busy = [(datetime.combine(DAY, time.min), datetime.combine(DAY + timedelta(days=1), time.min))]
    assert slots(30, busy=busy) == []


def test_time_grid_includes_closing(tmp_path):
    from tests.conftest import make_config

    config = make_config(tmp_path, work_start=time(10), work_end=time(12), slot_step=45)
    assert [hm(t) for t in time_grid(DAY, config)] == ["10:00", "10:45", "11:30", "12:00"]
