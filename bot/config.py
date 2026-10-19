"""Настройки бота из .env. Все проверки значений — здесь, в одной Pydantic-модели."""

from datetime import date, datetime, time
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# NoDecode: строку "1,2" из .env разбираем сами, а не как JSON
IntList = Annotated[tuple[int, ...], NoDecode]


def _split_ints(value: object) -> object:
    if isinstance(value, str):
        return tuple(int(part) for part in value.split(",") if part.strip())
    return value


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    bot_token: str = Field(pattern=r"^\d+:[\w-]+$")
    admin_ids: IntList = ()
    salon_name: str = Field("Барбершоп «Демо»", min_length=1, max_length=64)
    timezone: str = "Europe/Moscow"
    work_start: time = time(10)
    work_end: time = time(20)
    slot_step: int = Field(30, ge=5, le=240)  # шаг сетки записи, минут
    days_ahead: int = Field(14, ge=1, le=90)  # на сколько дней вперёд открыта запись
    reminder_hours: IntList = (24, 2)
    max_active_bookings: int = Field(3, ge=1, le=20)
    db_path: Path = Path("data/bot.db")

    @field_validator("admin_ids", "reminder_hours", mode="before")
    @classmethod
    def _parse_int_list(cls, value: object) -> object:
        return _split_ints(value)

    @field_validator("admin_ids")
    @classmethod
    def _check_admin_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(admin_id <= 0 for admin_id in value):
            raise ValueError("Telegram ID — положительные числа")
        return value

    @field_validator("reminder_hours")
    @classmethod
    def _check_reminders(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(not 1 <= h <= 168 for h in value):
            raise ValueError("напоминать можно за 1–168 часов")
        return tuple(sorted(set(value), reverse=True))

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"неизвестный часовой пояс {value!r}") from None
        return value

    @field_validator("db_path")
    @classmethod
    def _absolute_db_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else BASE_DIR / value

    @model_validator(mode="after")
    def _check_work_hours(self) -> "Config":
        if self.work_start >= self.work_end:
            raise ValueError("WORK_START должно быть раньше WORK_END")
        day = date.today()
        minutes = (
            datetime.combine(day, self.work_end) - datetime.combine(day, self.work_start)
        ).seconds // 60
        if self.slot_step > minutes:
            raise ValueError("SLOT_STEP больше рабочего дня")
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def now(self) -> datetime:
        """Текущее время салона без секунд. В базе всё хранится в этом поясе."""
        return datetime.now(self.tz).replace(tzinfo=None, second=0, microsecond=0)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_config() -> Config:
    try:
        return Config()
    except ValidationError as e:
        problems = "\n".join(
            f"  {'.'.join(map(str, err['loc'])).upper() or 'настройки'}: {err['msg']}"
            for err in e.errors()
        )
        raise RuntimeError(f"Ошибка в настройках .env:\n{problems}") from None
