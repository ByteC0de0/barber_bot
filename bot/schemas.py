"""Проверка данных записи и закрытия времени — все бизнес-правила в одном месте.

Модели проверяются с контекстом: model_validate(data, context={...}).
В контексте лежат config, now и (для записи) свободные слоты дня —
их нужно заранее достать из базы, потому что валидаторы Pydantic синхронные.
"""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from bot.config import Config
from bot.database import Service
from bot.scheduling import time_grid


def _fail(message: str) -> PydanticCustomError:
    return PydanticCustomError("booking_rule", message)


def first_error(error: ValidationError) -> str:
    """Текст первой ошибки — его показываем пользователю."""
    return error.errors()[0]["msg"]


def _context(info: ValidationInfo) -> tuple[Config, datetime, dict[str, Any]]:
    ctx = info.context or {}
    if "config" not in ctx or "now" not in ctx:
        raise RuntimeError("Для проверки нужен context={'config': ..., 'now': ...}")
    return ctx["config"], ctx["now"], ctx


class BookingRequest(BaseModel):
    """Запись, которую клиент собирается подтвердить. Если модель создана — всё заполнено и корректно."""

    model_config = ConfigDict(frozen=True)

    service: Service
    start: datetime
    user_id: int = Field(gt=0)
    client_name: str = Field(min_length=1, max_length=128)
    client_username: str | None = Field(None, max_length=32)

    @field_validator("client_name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("service")
    @classmethod
    def _check_service(cls, service: Service) -> Service:
        if service.duration <= 0 or service.price < 0:
            raise _fail("У услуги некорректная цена или длительность")
        return service

    @model_validator(mode="after")
    def _check_time(self, info: ValidationInfo) -> "BookingRequest":
        config, now, ctx = _context(info)
        start, end = self.start, self.end
        today = now.date()

        if start <= now:
            raise _fail("Это время уже прошло. Выберите другое.")
        if start.date() >= today + timedelta(days=config.days_ahead):
            raise _fail(f"Запись открыта только на {config.days_ahead} дней вперёд.")
        opening = datetime.combine(start.date(), config.work_start)
        closing = datetime.combine(start.date(), config.work_end)
        if start < opening or end > closing:
            raise _fail(
                f"Салон работает с {config.work_start:%H:%M} до {config.work_end:%H:%M} — "
                "услуга не помещается в это время."
            )
        if (start - opening) % timedelta(minutes=config.slot_step):
            raise _fail("На это время записаться нельзя. Выберите время из списка.")
        free_slots = ctx.get("free_slots")
        if free_slots is None:
            raise RuntimeError("Для проверки записи нужен context['free_slots']")
        if start not in free_slots:
            raise _fail("Увы, это время уже занято. Выберите другое.")
        return self

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.service.duration)


class BlockRequest(BaseModel):
    """Закрытие времени мастером: выходной (весь день) или перерыв."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    reason: str = Field(min_length=1, max_length=64)

    @property
    def is_full_day(self) -> bool:
        return self.start.time() == datetime.min.time() and self.end - self.start == timedelta(days=1)

    @model_validator(mode="after")
    def _check_period(self, info: ValidationInfo) -> "BlockRequest":
        config, now, _ = _context(info)
        if self.end <= self.start:
            raise _fail("Конец перерыва должен быть позже начала.")
        if self.end <= now:
            raise _fail("Это время уже прошло.")
        if self.start.date() >= now.date() + timedelta(days=config.days_ahead):
            raise _fail(f"Закрыть время можно только на {config.days_ahead} дней вперёд.")
        if not self.is_full_day:
            grid = time_grid(self.start.date(), config)
            if self.start not in grid or self.end not in grid:
                raise _fail("Перерыв должен быть в рабочие часы и по сетке записи.")
        return self
