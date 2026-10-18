import asyncio
from datetime import time
from zoneinfo import ZoneInfo

import pytest

from bot.config import Config
from bot.database import Database

ADMIN_ID = 1000


def make_config(tmp_path, **overrides) -> Config:
    values = dict(
        bot_token="123456:TEST",
        admin_ids=frozenset({ADMIN_ID}),
        salon_name="Тестовый салон",
        tz=ZoneInfo("Europe/Moscow"),
        work_start=time(10),
        work_end=time(20),
        slot_step=30,
        days_ahead=14,
        reminder_hours=(24, 2),
        max_active_bookings=3,
        db_path=tmp_path / "test.db",
    )
    values.update(overrides)
    return Config(**values)


@pytest.fixture
def config(tmp_path) -> Config:
    return make_config(tmp_path)


@pytest.fixture
def db(config) -> Database:
    database = Database(config.db_path)
    asyncio.run(database.init())
    return database
