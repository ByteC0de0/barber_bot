"""Настройки бота. Читаем их из файла .env, чтобы не хранить секреты в коде."""

import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Подгружаем переменные из .env в окружение процесса (os.environ)
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    salon_name: str
    tz: ZoneInfo
    work_start: time
    work_end: time
    slot_step: int  # шаг сетки записи, минут
    days_ahead: int  # на сколько дней вперёд открыта запись
    reminder_hours: tuple[int, ...]
    max_active_bookings: int
    db_path: Path

    def now(self) -> datetime:
        """Текущее время салона без секунд. В базе всё хранится в этом поясе."""
        return datetime.now(self.tz).replace(tzinfo=None, second=0, microsecond=0)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    value = _get(name, str(default))
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"{name} должно быть числом, а сейчас: {value!r}") from None


def _int_list(name: str, default: str) -> tuple[int, ...]:
    value = _get(name, default)
    try:
        return tuple(int(part) for part in value.split(",") if part.strip())
    except ValueError:
        raise RuntimeError(
            f"{name} — числа через запятую, а сейчас: {value!r}"
        ) from None


def _time(name: str, default: str) -> time:
    value = _get(name, default)
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise RuntimeError(f"{name} — время в формате ЧЧ:ММ, а сейчас: {value!r}") from None


def load_config() -> Config:
    token = _get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Открой файл .env и впиши токен от @BotFather."
        )

    tz_name = _get("TIMEZONE", "Europe/Moscow")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise RuntimeError(f"Неизвестный часовой пояс TIMEZONE={tz_name!r}") from None

    work_start = _time("WORK_START", "10:00")
    work_end = _time("WORK_END", "20:00")
    if work_start >= work_end:
        raise RuntimeError("WORK_START должно быть раньше WORK_END")

    db_path = Path(_get("DB_PATH", "data/bot.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    return Config(
        bot_token=token,
        admin_ids=frozenset(_int_list("ADMIN_IDS", "")),
        salon_name=_get("SALON_NAME", "Барбершоп «Демо»"),
        tz=tz,
        work_start=work_start,
        work_end=work_end,
        slot_step=_int("SLOT_STEP", 30),
        days_ahead=_int("DAYS_AHEAD", 14),
        reminder_hours=tuple(sorted(set(_int_list("REMINDER_HOURS", "24,2")), reverse=True)),
        max_active_bookings=_int("MAX_ACTIVE_BOOKINGS", 3),
        db_path=db_path,
    )
