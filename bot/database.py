"""Работа с базой SQLite: услуги, записи, закрытое время, отправленные напоминания.

Даты хранятся строками "ГГГГ-ММ-ДД ЧЧ:ММ" в часовом поясе салона —
такие строки правильно сравниваются прямо в SQL.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import aiosqlite

DT_FORMAT = "%Y-%m-%d %H:%M"

# Услуги, которые создаются при первом запуске (название, цена ₽, длительность мин)
DEFAULT_SERVICES = [
    ("Мужская стрижка", 1500, 60),
    ("Стрижка машинкой", 900, 30),
    ("Оформление бороды", 800, 30),
    ("Стрижка + борода", 2100, 90),
    ("Детская стрижка", 1000, 45),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    price     INTEGER NOT NULL,
    duration  INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    client_name     TEXT    NOT NULL,
    client_username TEXT,
    service_id      INTEGER NOT NULL REFERENCES services (id),
    start_at        TEXT    NOT NULL,
    end_at          TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'active',  -- active | cancelled
    cancelled_by    TEXT,                               -- client | admin
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings (start_at);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id);

CREATE TABLE IF NOT EXISTS blocks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    start_at TEXT NOT NULL,
    end_at   TEXT NOT NULL,
    reason   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_reminders (
    booking_id   INTEGER NOT NULL REFERENCES bookings (id),
    hours_before INTEGER NOT NULL,
    PRIMARY KEY (booking_id, hours_before)
);
"""


def to_db(dt: datetime) -> str:
    return dt.strftime(DT_FORMAT)


def from_db(value: str) -> datetime:
    return datetime.strptime(value, DT_FORMAT)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


@dataclass(frozen=True)
class Service:
    id: int
    name: str
    price: int
    duration: int  # минут


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    client_name: str
    client_username: str | None
    service_id: int
    service_name: str
    price: int
    start: datetime
    end: datetime
    status: str
    created_at: datetime


@dataclass(frozen=True)
class Block:
    id: int
    start: datetime
    end: datetime
    reason: str

    @property
    def is_full_day(self) -> bool:
        return self.start.time() == time.min and self.end - self.start == timedelta(days=1)


_BOOKING_SELECT = """
SELECT b.id, b.user_id, b.client_name, b.client_username, b.service_id,
       s.name AS service_name, s.price, b.start_at, b.end_at, b.status, b.created_at
FROM bookings AS b
JOIN services AS s ON s.id = b.service_id
"""


def _booking(row: aiosqlite.Row) -> Booking:
    return Booking(
        id=row["id"],
        user_id=row["user_id"],
        client_name=row["client_name"],
        client_username=row["client_username"],
        service_id=row["service_id"],
        service_name=row["service_name"],
        price=row["price"],
        start=from_db(row["start_at"]),
        end=from_db(row["end_at"]),
        status=row["status"],
        created_at=from_db(row["created_at"]),
    )


def _block(row: aiosqlite.Row) -> Block:
    return Block(
        id=row["id"],
        start=from_db(row["start_at"]),
        end=from_db(row["end_at"]),
        reason=row["reason"],
    )


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            yield conn

    async def init(self) -> None:
        """Создаёт таблицы и демо-услуги при первом запуске."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as conn:
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.executescript(SCHEMA)
            cursor = await conn.execute("SELECT COUNT(*) FROM services")
            (count,) = await cursor.fetchone()
            if count == 0:
                await conn.executemany(
                    "INSERT INTO services (name, price, duration) VALUES (?, ?, ?)",
                    DEFAULT_SERVICES,
                )
            await conn.commit()

    # --- Услуги ---

    async def get_services(self) -> list[Service]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT id, name, price, duration FROM services"
                " WHERE is_active = 1 ORDER BY id"
            )
            return [Service(**dict(row)) for row in await cursor.fetchall()]

    async def get_service(self, service_id: int) -> Service | None:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT id, name, price, duration FROM services"
                " WHERE id = ? AND is_active = 1",
                (service_id,),
            )
            row = await cursor.fetchone()
            return Service(**dict(row)) if row else None

    # --- Занятость ---

    async def get_busy_intervals(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Активные записи и закрытое время, пересекающие промежуток [start, end)."""
        params = (to_db(end), to_db(start))
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT start_at, end_at FROM bookings
                WHERE status = 'active' AND start_at < ? AND end_at > ?
                UNION ALL
                SELECT start_at, end_at FROM blocks
                WHERE start_at < ? AND end_at > ?
                """,
                params * 2,
            )
            return [(from_db(r[0]), from_db(r[1])) for r in await cursor.fetchall()]

    @staticmethod
    async def _overlapping_bookings(
        conn: aiosqlite.Connection, start: datetime, end: datetime
    ) -> list[Booking]:
        cursor = await conn.execute(
            _BOOKING_SELECT
            + " WHERE b.status = 'active' AND b.start_at < ? AND b.end_at > ?"
            " ORDER BY b.start_at",
            (to_db(end), to_db(start)),
        )
        return [_booking(row) for row in await cursor.fetchall()]

    @staticmethod
    async def _has_block(conn: aiosqlite.Connection, start: datetime, end: datetime) -> bool:
        cursor = await conn.execute(
            "SELECT 1 FROM blocks WHERE start_at < ? AND end_at > ? LIMIT 1",
            (to_db(end), to_db(start)),
        )
        return await cursor.fetchone() is not None

    # --- Записи ---

    async def create_booking(
        self,
        *,
        user_id: int,
        client_name: str,
        client_username: str | None,
        service: Service,
        start: datetime,
        now: datetime,
    ) -> Booking | None:
        """Создаёт запись. Возвращает None, если время уже занято или закрыто."""
        end = start + timedelta(minutes=service.duration)
        async with self._connect() as conn:
            # BEGIN IMMEDIATE сразу берёт блокировку на запись: если два клиента
            # одновременно жмут «Подтвердить», второй дождётся первого и увидит,
            # что время уже занято.
            await conn.execute("BEGIN IMMEDIATE")
            if await self._overlapping_bookings(conn, start, end) or await self._has_block(
                conn, start, end
            ):
                await conn.rollback()
                return None
            cursor = await conn.execute(
                """
                INSERT INTO bookings
                    (user_id, client_name, client_username, service_id,
                     start_at, end_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    client_name,
                    client_username,
                    service.id,
                    to_db(start),
                    to_db(end),
                    to_db(now),
                ),
            )
            booking_id = cursor.lastrowid
            await conn.commit()
        return await self.get_booking(booking_id)

    async def get_booking(self, booking_id: int) -> Booking | None:
        async with self._connect() as conn:
            cursor = await conn.execute(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,))
            row = await cursor.fetchone()
            return _booking(row) if row else None

    async def cancel_booking(self, booking_id: int, by: str) -> bool:
        """Отменяет активную запись. False — запись уже была отменена."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                "UPDATE bookings SET status = 'cancelled', cancelled_by = ?"
                " WHERE id = ? AND status = 'active'",
                (by, booking_id),
            )
            await conn.commit()
            return cursor.rowcount == 1

    async def get_user_upcoming(self, user_id: int, now: datetime) -> list[Booking]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                _BOOKING_SELECT
                + " WHERE b.user_id = ? AND b.status = 'active' AND b.start_at > ?"
                " ORDER BY b.start_at",
                (user_id, to_db(now)),
            )
            return [_booking(row) for row in await cursor.fetchall()]

    async def get_day_bookings(self, day: date) -> list[Booking]:
        start, end = day_bounds(day)
        async with self._connect() as conn:
            cursor = await conn.execute(
                _BOOKING_SELECT
                + " WHERE b.status = 'active' AND b.start_at >= ? AND b.start_at < ?"
                " ORDER BY b.start_at",
                (to_db(start), to_db(end)),
            )
            return [_booking(row) for row in await cursor.fetchall()]

    async def get_bookings_starting_between(
        self, after: datetime, until: datetime
    ) -> list[Booking]:
        """Активные записи, которые начинаются в промежутке (after, until]."""
        async with self._connect() as conn:
            cursor = await conn.execute(
                _BOOKING_SELECT
                + " WHERE b.status = 'active' AND b.start_at > ? AND b.start_at <= ?"
                " ORDER BY b.start_at",
                (to_db(after), to_db(until)),
            )
            return [_booking(row) for row in await cursor.fetchall()]

    # --- Закрытое время (выходные, перерывы) ---

    async def create_block(
        self, start: datetime, end: datetime, reason: str
    ) -> tuple[Block | None, list[Booking]]:
        """Закрывает время. Если на него уже есть записи — ничего не создаёт
        и возвращает (None, список мешающих записей)."""
        async with self._connect() as conn:
            await conn.execute("BEGIN IMMEDIATE")
            conflicts = await self._overlapping_bookings(conn, start, end)
            if conflicts:
                await conn.rollback()
                return None, conflicts
            cursor = await conn.execute(
                "INSERT INTO blocks (start_at, end_at, reason) VALUES (?, ?, ?)",
                (to_db(start), to_db(end), reason),
            )
            await conn.commit()
            return Block(id=cursor.lastrowid, start=start, end=end, reason=reason), []

    async def get_day_blocks(self, day: date) -> list[Block]:
        start, end = day_bounds(day)
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM blocks WHERE start_at < ? AND end_at > ? ORDER BY start_at",
                (to_db(end), to_db(start)),
            )
            return [_block(row) for row in await cursor.fetchall()]

    async def get_upcoming_blocks(self, now: datetime) -> list[Block]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM blocks WHERE end_at > ? ORDER BY start_at", (to_db(now),)
            )
            return [_block(row) for row in await cursor.fetchall()]

    async def delete_block(self, block_id: int) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
            await conn.commit()
            return cursor.rowcount == 1

    # --- Напоминания ---

    async def get_sent_reminders(self, booking_id: int) -> set[int]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT hours_before FROM sent_reminders WHERE booking_id = ?", (booking_id,)
            )
            return {row[0] for row in await cursor.fetchall()}

    async def mark_reminder_sent(self, booking_id: int, hours_before: int) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO sent_reminders (booking_id, hours_before) VALUES (?, ?)",
                (booking_id, hours_before),
            )
            await conn.commit()
