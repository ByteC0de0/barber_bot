"""Напоминания клиентам перед визитом.

Раз в минуту фоновая задача смотрит, кому пора напомнить. Что уже отправлено,
хранится в базе — поэтому после перезапуска бота напоминания не дублируются.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, html
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from bot import formatting as fmt
from bot.config import Config
from bot.database import Booking, Database
from bot.keyboards.client import reminder_kb

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # секунд


def due_reminders(booking: Booking, hours: tuple[int, ...], sent: set[int], now: datetime) -> list[int]:
    """Какие напоминания (за сколько часов) пора отправить по этой записи.

    Напоминание за N часов не шлём, если клиент записался уже позже этого
    момента: записался за час до визита — напоминать «за 24 часа» бессмысленно.
    """
    due = []
    for h in hours:
        moment = booking.start - timedelta(hours=h)
        if h not in sent and moment <= now and booking.created_at <= moment:
            due.append(h)
    return due


def reminder_text(booking: Booking, config: Config, now: datetime) -> str:
    when = fmt.relative_day(booking.start.date(), now.date())
    return (
        f"⏰ {html.bold('Напоминание о записи')}\n\n"
        f"Ждём вас {when} в {fmt.hm(booking.start)} в {html.quote(config.salon_name)}.\n\n"
        f"{fmt.booking_details(booking)}\n\n"
        "Если планы изменились — отмените запись, чтобы освободить время."
    )


async def send_due_reminders(
    bot: Bot, db: Database, config: Config, now: datetime | None = None
) -> int:
    """Отправляет все напоминания, которым пришло время. Возвращает, сколько отправлено."""
    if not config.reminder_hours:
        return 0
    now = now or config.now()
    horizon = now + timedelta(hours=max(config.reminder_hours))
    sent_count = 0

    for booking in await db.get_bookings_starting_between(now, horizon):
        due = due_reminders(booking, config.reminder_hours, await db.get_sent_reminders(booking.id), now)
        if not due:
            continue
        try:
            # Если бот был выключен и пропустил несколько напоминаний —
            # отправляем одно, а не пачку.
            await bot.send_message(
                booking.user_id,
                reminder_text(booking, config, now),
                reply_markup=reminder_kb(booking.id),
            )
            sent_count += 1
        except TelegramForbiddenError:
            logger.info("Клиент %s заблокировал бота, напоминание пропущено", booking.user_id)
        except TelegramAPIError as e:
            # Например, нет сети — попробуем снова на следующем круге
            logger.warning("Не удалось отправить напоминание по записи %s: %s", booking.id, e)
            continue
        for h in due:
            await db.mark_reminder_sent(booking.id, h)

    return sent_count


async def reminder_loop(bot: Bot, db: Database, config: Config) -> None:
    logger.info("Напоминания включены: за %s ч до визита", ", ".join(map(str, config.reminder_hours)))
    while True:
        try:
            await send_due_reminders(bot, db, config)
        except Exception:
            logger.exception("Ошибка при отправке напоминаний")
        await asyncio.sleep(CHECK_INTERVAL)
