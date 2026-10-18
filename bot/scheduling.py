"""Расчёт свободного времени для записи и сетки времени для админа."""

from datetime import date, datetime, time, timedelta

from bot.config import Config
from bot.database import Database

Interval = tuple[datetime, datetime]


def overlaps(start: datetime, end: datetime, busy: list[Interval]) -> bool:
    """Пересекается ли [start, end) хотя бы с одним занятым промежутком."""
    return any(b_start < end and b_end > start for b_start, b_end in busy)


def day_slots(
    day: date,
    duration: int,
    busy: list[Interval],
    now: datetime,
    *,
    work_start: time,
    work_end: time,
    step: int,
) -> list[datetime]:
    """Время начала, на которое можно записаться на услугу длительностью duration минут."""
    length = timedelta(minutes=duration)
    closing = datetime.combine(day, work_end)
    slot = datetime.combine(day, work_start)
    result = []
    while slot + length <= closing:
        if slot > now and not overlaps(slot, slot + length, busy):
            result.append(slot)
        slot += timedelta(minutes=step)
    return result


def booking_days(config: Config) -> list[date]:
    """Дни, на которые открыта запись: сегодня и дальше на days_ahead дней."""
    today = config.now().date()
    return [today + timedelta(days=i) for i in range(config.days_ahead)]


async def free_slots(
    db: Database, config: Config, duration: int, days: list[date]
) -> dict[date, list[datetime]]:
    """Свободные слоты по дням. Дни без свободного времени в результат не попадают."""
    if not days:
        return {}
    now = config.now()
    busy = await db.get_busy_intervals(
        datetime.combine(min(days), time.min),
        datetime.combine(max(days) + timedelta(days=1), time.min),
    )
    result = {}
    for day in days:
        slots = day_slots(
            day,
            duration,
            busy,
            now,
            work_start=config.work_start,
            work_end=config.work_end,
            step=config.slot_step,
        )
        if slots:
            result[day] = slots
    return result


def time_grid(day: date, config: Config) -> list[datetime]:
    """Все отметки сетки рабочего дня, от открытия до закрытия включительно."""
    point = datetime.combine(day, config.work_start)
    closing = datetime.combine(day, config.work_end)
    result = []
    while point <= closing:
        result.append(point)
        point += timedelta(minutes=config.slot_step)
    if result[-1] != closing:
        result.append(closing)
    return result
