from datetime import datetime, timedelta

from bot.database import day_bounds
from tests.helpers import async_test

START = datetime(2030, 1, 15, 12, 0)
NOW = datetime(2030, 1, 1, 9, 0)


async def book(db, start, service_index=0, user_id=1):
    service = (await db.get_services())[service_index]
    return await db.create_booking(
        user_id=user_id,
        client_name="Иван",
        client_username=None,
        service=service,
        start=start,
        now=NOW,
    )


@async_test
async def test_demo_services_created(db):
    services = await db.get_services()
    assert len(services) == 5
    assert services[0].name == "Мужская стрижка"


@async_test
async def test_overlapping_booking_rejected(db):
    first = await book(db, START)  # 60 минут: 12:00–13:00
    assert first is not None and first.end == START + timedelta(hours=1)
    assert await book(db, START + timedelta(minutes=30), user_id=2) is None
    assert await book(db, START - timedelta(minutes=30), user_id=2) is None
    # Впритык — можно
    assert await book(db, START + timedelta(hours=1), user_id=2) is not None
    assert await book(db, START - timedelta(hours=1), user_id=2) is not None


@async_test
async def test_cancel_frees_time(db):
    booking = await book(db, START)
    assert await db.cancel_booking(booking.id, by="client") is True
    assert await db.cancel_booking(booking.id, by="client") is False
    assert await book(db, START, user_id=2) is not None


@async_test
async def test_block_prevents_booking_and_conflicts_reported(db):
    block, conflicts = await db.create_block(START, START + timedelta(hours=2), "Перерыв")
    assert block is not None and conflicts == []
    assert await book(db, START + timedelta(minutes=30)) is None

    booking = await book(db, START + timedelta(hours=3))
    block, conflicts = await db.create_block(*day_bounds(START.date()), "Выходной")
    assert block is None
    assert [b.id for b in conflicts] == [booking.id]
