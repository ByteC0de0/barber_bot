"""Запись клиента: услуга → дата → время → подтверждение."""

from datetime import date, timedelta

from aiogram import Bot, F, Router, html
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import formatting as fmt
from bot.callbacks import (
    BOOK_ABORT,
    BOOK_SERVICES,
    ConfirmCb,
    DayCb,
    ServiceCb,
    SlotCb,
    unpack_day,
    unpack_dt,
)
from bot.config import Config
from bot.database import Database, Service
from bot.keyboards.client import (
    BTN_BOOK,
    back_to_services_kb,
    confirm_kb,
    days_kb,
    services_kb,
    slots_kb,
)
from bot.messaging import edit_message, notify_admins
from bot.scheduling import booking_days, free_slots

router = Router()

CHOOSE_SERVICE = "Выберите услугу:"


async def _limit_error(user_id: int, db: Database, config: Config) -> str | None:
    """Текст ошибки, если у клиента уже максимум активных записей."""
    upcoming = await db.get_user_upcoming(user_id, config.now())
    if len(upcoming) >= config.max_active_bookings:
        return (
            f"Активных записей: {len(upcoming)} — это максимум. "
            "Отмените одну в «Мои записи», чтобы записаться снова."
        )
    return None


def _service_header(service: Service) -> str:
    return (
        f"💈 {html.bold(html.quote(service.name))}\n"
        f"{fmt.price(service.price)} · {fmt.duration(service.duration)}"
    )


async def _show_days(
    callback: CallbackQuery, service: Service, db: Database, config: Config
) -> None:
    slots = await free_slots(db, config, service.duration, booking_days(config))
    if not slots:
        await edit_message(
            callback,
            f"{_service_header(service)}\n\n"
            f"К сожалению, в ближайшие {config.days_ahead} дней свободного времени нет 😔",
            back_to_services_kb(),
        )
        return
    await edit_message(
        callback,
        f"{_service_header(service)}\n\nВыберите дату:",
        days_kb(service.id, list(slots)),
    )


async def _show_slots(
    callback: CallbackQuery, service: Service, day: date, db: Database, config: Config
) -> None:
    slots = []
    if day in booking_days(config):
        slots = (await free_slots(db, config, service.duration, [day])).get(day, [])
    if not slots:
        await _show_days(callback, service, db, config)
        return
    await edit_message(
        callback,
        f"{_service_header(service)}\n📅 {fmt.day_long(day)}\n\nВыберите время:",
        slots_kb(service.id, slots),
    )


async def _get_service(callback: CallbackQuery, service_id: int, db: Database) -> Service | None:
    service = await db.get_service(service_id)
    if service is None:
        await callback.answer("Эта услуга больше недоступна", show_alert=True)
    return service


@router.message(Command("book"))
@router.message(F.text == BTN_BOOK)
async def start_booking(message: Message, db: Database, config: Config) -> None:
    if error := await _limit_error(message.from_user.id, db, config):
        await message.answer(error)
        return
    await message.answer(CHOOSE_SERVICE, reply_markup=services_kb(await db.get_services()))


@router.callback_query(F.data == BOOK_SERVICES)
async def back_to_services(callback: CallbackQuery, db: Database, config: Config) -> None:
    if error := await _limit_error(callback.from_user.id, db, config):
        await callback.answer(error, show_alert=True)
        return
    await edit_message(callback, CHOOSE_SERVICE, services_kb(await db.get_services()))
    await callback.answer()


@router.callback_query(ServiceCb.filter())
async def choose_day(
    callback: CallbackQuery, callback_data: ServiceCb, db: Database, config: Config
) -> None:
    if service := await _get_service(callback, callback_data.service_id, db):
        await _show_days(callback, service, db, config)
        await callback.answer()


@router.callback_query(DayCb.filter())
async def choose_slot(
    callback: CallbackQuery, callback_data: DayCb, db: Database, config: Config
) -> None:
    if service := await _get_service(callback, callback_data.service_id, db):
        await _show_slots(callback, service, unpack_day(callback_data.day), db, config)
        await callback.answer()


@router.callback_query(SlotCb.filter())
async def review_booking(
    callback: CallbackQuery, callback_data: SlotCb, db: Database
) -> None:
    service = await _get_service(callback, callback_data.service_id, db)
    if service is None:
        return
    start = unpack_dt(callback_data.at)
    end = start + timedelta(minutes=service.duration)
    await edit_message(
        callback,
        "Проверьте запись:\n\n"
        f"💈 {html.bold(html.quote(service.name))}\n"
        f"📅 {fmt.day_long(start.date())}\n"
        f"🕐 {fmt.hm(start)}–{fmt.hm(end)}\n"
        f"💰 {fmt.price(service.price)}",
        confirm_kb(service.id, start),
    )
    await callback.answer()


@router.callback_query(ConfirmCb.filter())
async def confirm_booking(
    callback: CallbackQuery,
    callback_data: ConfirmCb,
    db: Database,
    config: Config,
    bot: Bot,
) -> None:
    service = await _get_service(callback, callback_data.service_id, db)
    if service is None:
        return
    user = callback.from_user
    if error := await _limit_error(user.id, db, config):
        await callback.answer(error, show_alert=True)
        return

    # Пока клиент думал, время могли занять, закрыть или оно могло пройти —
    # проверяем заново по актуальным данным.
    start = unpack_dt(callback_data.at)
    booking = None
    if start.date() in booking_days(config):
        day_free = await free_slots(db, config, service.duration, [start.date()])
        if start in day_free.get(start.date(), []):
            booking = await db.create_booking(
                user_id=user.id,
                client_name=user.full_name,
                client_username=user.username,
                service=service,
                start=start,
                now=config.now(),
            )

    if booking is None:
        await callback.answer(
            "Увы, это время уже занято или прошло. Выберите другое.", show_alert=True
        )
        await _show_slots(callback, service, start.date(), db, config)
        return

    await edit_message(
        callback,
        f"✅ {html.bold('Вы записаны!')}\n\n{fmt.booking_details(booking)}\n\n"
        "Я пришлю напоминание перед визитом. "
        "Отменить запись можно в разделе «📋 Мои записи».",
    )
    await callback.answer("Готово!")
    await notify_admins(
        bot,
        config,
        f"🆕 {html.bold('Новая запись')}\n\n"
        f"{fmt.booking_details(booking)}\n👤 {fmt.client_mention(booking)}",
    )


@router.callback_query(F.data == BOOK_ABORT)
async def abort_booking(callback: CallbackQuery) -> None:
    await edit_message(
        callback, "Запись не оформлена. Нажмите «📅 Записаться», чтобы начать заново."
    )
    await callback.answer()
