from datetime import datetime, time, timedelta

from bot.reminders import send_due_reminders
from tests.helpers import CLIENT, Harness, async_test


async def make_booking(db, start, created):
    service = (await db.get_services())[0]
    return await db.create_booking(
        user_id=CLIENT.id,
        client_name="Иван",
        client_username="ivan",
        service=service,
        start=start,
        now=created,
    )


def visit(config):
    return datetime.combine(config.now().date() + timedelta(days=3), time(12))


@async_test
async def test_reminders_24h_and_2h_sent_once(config, db):
    h = Harness(config, db)
    start = visit(config)
    await make_booking(db, start, created=start - timedelta(days=2))

    async def run(before):
        return await send_due_reminders(h.bot, db, config, now=start - before)

    assert await run(timedelta(hours=25)) == 0
    assert await run(timedelta(hours=24)) == 1
    assert "Напоминание" in h.last(CLIENT.id).text
    assert "завтра" in h.last(CLIENT.id).text
    assert await run(timedelta(hours=23)) == 0  # не дублируем
    assert await run(timedelta(hours=2)) == 1
    assert "сегодня" in h.last(CLIENT.id).text
    assert await run(timedelta(minutes=30)) == 0


@async_test
async def test_no_reminders_for_last_minute_booking(config, db):
    h = Harness(config, db)
    start = visit(config)
    await make_booking(db, start, created=start - timedelta(hours=1))
    assert await send_due_reminders(h.bot, db, config, now=start - timedelta(minutes=50)) == 0


@async_test
async def test_booking_made_same_day_gets_only_2h_reminder(config, db):
    h = Harness(config, db)
    start = visit(config)
    await make_booking(db, start, created=start - timedelta(hours=5))
    assert await send_due_reminders(h.bot, db, config, now=start - timedelta(hours=4)) == 0
    assert await send_due_reminders(h.bot, db, config, now=start - timedelta(hours=2)) == 1


@async_test
async def test_missed_reminders_collapse_into_one(config, db):
    h = Harness(config, db)
    start = visit(config)
    booking = await make_booking(db, start, created=start - timedelta(days=2))
    # Бот был выключен и пропустил оба момента
    assert await send_due_reminders(h.bot, db, config, now=start - timedelta(hours=1)) == 1
    assert await db.get_sent_reminders(booking.id) == {24, 2}


@async_test
async def test_cancelled_booking_not_reminded(config, db):
    h = Harness(config, db)
    start = visit(config)
    booking = await make_booking(db, start, created=start - timedelta(days=2))
    await db.cancel_booking(booking.id, by="client")
    assert await send_due_reminders(h.bot, db, config, now=start - timedelta(hours=24)) == 0
