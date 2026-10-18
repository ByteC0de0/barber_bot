"""Админ-панель мастера: записи на день, отмена, закрытие и открытие времени."""

from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router, html
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import formatting as fmt
from bot.callbacks import AdminCb, unpack_day, unpack_dt
from bot.config import Config
from bot.database import Database, day_bounds
from bot.filters import IsAdmin
from bot.keyboards import admin as kb
from bot.keyboards.client import BTN_ADMIN, BTN_BOOK
from bot.messaging import edit_message, send_safe
from bot.scheduling import booking_days, time_grid

router = Router()
# Все обработчики этого роутера доступны только админам
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MENU_TEXT = f"🛠 {html.bold('Админ-панель')}\n\nЧто нужно сделать?"


def action(name: str):
    return AdminCb.filter(F.action == name)


# --- Меню ---


@router.message(Command("admin"))
@router.message(F.text == BTN_ADMIN)
async def admin_menu(message: Message) -> None:
    await message.answer(MENU_TEXT, reply_markup=kb.admin_menu_kb())


@router.callback_query(action("menu"))
async def admin_menu_cb(callback: CallbackQuery) -> None:
    await edit_message(callback, MENU_TEXT, kb.admin_menu_kb())
    await callback.answer()


# --- Записи на день ---


async def _show_day(callback: CallbackQuery, day: date, db: Database, config: Config) -> None:
    bookings = await db.get_day_bookings(day)
    blocks = await db.get_day_blocks(day)

    events: list[tuple[datetime, str]] = [
        (
            b.start,
            f"🕐 {html.bold(fmt.hm(b.start))}–{fmt.hm(b.end)} · "
            f"{html.quote(b.service_name)} · {fmt.client_mention(b)}",
        )
        for b in bookings
    ]
    for block in blocks:
        period = (
            "весь день" if block.is_full_day else f"{fmt.hm(block.start)}–{fmt.hm(block.end)}"
        )
        events.append((block.start, f"⛔ {period} · {html.quote(block.reason)}"))
    events.sort(key=lambda event: event[0])

    lines = [f"📋 {html.bold(fmt.day_long(day))}", ""]
    if events:
        lines.extend(text for _, text in events)
    else:
        lines.append("Записей нет.")
    if bookings:
        total = sum(b.price for b in bookings)
        lines += ["", f"Записей: {len(bookings)} · Сумма: {fmt.price(total)}"]

    now = config.now()
    cancellable = [b for b in bookings if b.start > now]
    await edit_message(callback, "\n".join(lines), kb.day_kb(day, cancellable))


@router.callback_query(action("today"))
async def today(callback: CallbackQuery, db: Database, config: Config) -> None:
    await _show_day(callback, config.now().date(), db, config)
    await callback.answer()


@router.callback_query(action("pick_day"))
async def pick_day(callback: CallbackQuery, config: Config) -> None:
    await edit_message(
        callback, "📆 Выберите день:", kb.days_kb(booking_days(config), action="day")
    )
    await callback.answer()


@router.callback_query(action("day"))
async def show_day(
    callback: CallbackQuery, callback_data: AdminCb, db: Database, config: Config
) -> None:
    await _show_day(callback, unpack_day(callback_data.day), db, config)
    await callback.answer()


# --- Отмена записи мастером ---


@router.callback_query(action("cancel_ask"))
async def cancel_ask(
    callback: CallbackQuery, callback_data: AdminCb, db: Database, config: Config
) -> None:
    booking = await db.get_booking(callback_data.item_id)
    if booking is None or booking.status != "active":
        await callback.answer("Эта запись уже отменена", show_alert=True)
        if booking:
            await _show_day(callback, booking.start.date(), db, config)
        return
    await edit_message(
        callback,
        f"Отменить запись клиента?\n\n{fmt.booking_details(booking)}\n"
        f"👤 {fmt.client_mention(booking)}\n\nКлиент получит уведомление.",
        kb.cancel_confirm_kb(booking),
    )
    await callback.answer()


@router.callback_query(action("cancel"))
async def cancel_booking(
    callback: CallbackQuery, callback_data: AdminCb, db: Database, config: Config, bot: Bot
) -> None:
    booking = await db.get_booking(callback_data.item_id)
    if booking is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if await db.cancel_booking(booking.id, by="admin"):
        await send_safe(
            bot,
            booking.user_id,
            f"😔 {html.bold('Ваша запись отменена мастером')}\n\n"
            f"{fmt.booking_details(booking)}\n\n"
            f"Приносим извинения! Выберите другое время: «{BTN_BOOK}».",
        )
        await callback.answer("Запись отменена, клиент уведомлён")
    else:
        await callback.answer("Эта запись уже была отменена")
    await _show_day(callback, booking.start.date(), db, config)


# --- Закрыть время ---


@router.callback_query(action("block_pick"))
async def block_pick(callback: CallbackQuery, config: Config) -> None:
    await edit_message(
        callback,
        f"⛔ {html.bold('Закрыть время')}\n\nВыберите день:",
        kb.days_kb(booking_days(config), action="block_day"),
    )
    await callback.answer()


@router.callback_query(action("block_day"))
async def block_day(callback: CallbackQuery, callback_data: AdminCb, config: Config) -> None:
    day = unpack_day(callback_data.day)
    now = config.now()
    step = timedelta(minutes=config.slot_step)
    # Начать перерыв можно с любой отметки сетки, которая ещё не закончилась
    starts = [t for t in time_grid(day, config)[:-1] if t + step > now]
    await edit_message(
        callback,
        f"⛔ {html.bold(fmt.day_long(day))}\n\n"
        "Закрыть весь день или выберите, с какого времени перерыв:",
        kb.block_start_kb(day, starts),
    )
    await callback.answer()


@router.callback_query(action("block_from"))
async def block_from(callback: CallbackQuery, callback_data: AdminCb, config: Config) -> None:
    start = unpack_dt(callback_data.start)
    ends = [t for t in time_grid(start.date(), config) if t > start]
    await edit_message(
        callback,
        f"⛔ {html.bold(fmt.day_long(start.date()))}\n\n"
        f"Перерыв с {fmt.hm(start)} — до какого времени?",
        kb.block_end_kb(start, ends),
    )
    await callback.answer()


async def _create_block(
    callback: CallbackQuery, start: datetime, end: datetime, reason: str, db: Database
) -> None:
    block, conflicts = await db.create_block(start, end, reason)
    if block is None:
        lines = ["⚠️ Нельзя закрыть это время — на него есть записи:", ""]
        lines += [
            f"• {fmt.hm(b.start)} {html.quote(b.service_name)} — {fmt.client_mention(b)}"
            for b in conflicts
        ]
        lines += ["", "Сначала отмените их (клиенты получат уведомление)."]
        await edit_message(callback, "\n".join(lines), kb.block_conflict_kb(start.date()))
        await callback.answer()
        return
    await edit_message(
        callback,
        f"⛔ Время закрыто: {fmt.block_line(block)}\n"
        "Клиенты не смогут записаться на это время.",
        kb.back_to_menu_kb(),
    )
    await callback.answer("Готово")


@router.callback_query(action("block_full"))
async def block_full(callback: CallbackQuery, callback_data: AdminCb, db: Database) -> None:
    start, end = day_bounds(unpack_day(callback_data.day))
    await _create_block(callback, start, end, "Выходной", db)


@router.callback_query(action("block_to"))
async def block_to(callback: CallbackQuery, callback_data: AdminCb, db: Database) -> None:
    start = unpack_dt(callback_data.start)
    end = unpack_dt(callback_data.end)
    await _create_block(callback, start, end, "Перерыв", db)


# --- Открыть время ---


async def _show_blocks(callback: CallbackQuery, db: Database, config: Config) -> None:
    blocks = await db.get_upcoming_blocks(config.now())
    if blocks:
        text = (
            f"✅ {html.bold('Открыть время')}\n\n"
            "Нажмите на период, чтобы снова открыть его для записи:"
        )
    else:
        text = "Закрытого времени нет."
    await edit_message(callback, text, kb.blocks_kb(blocks))


@router.callback_query(action("blocks"))
async def blocks(callback: CallbackQuery, db: Database, config: Config) -> None:
    await _show_blocks(callback, db, config)
    await callback.answer()


@router.callback_query(action("unblock"))
async def unblock(
    callback: CallbackQuery, callback_data: AdminCb, db: Database, config: Config
) -> None:
    deleted = await db.delete_block(callback_data.item_id)
    await _show_blocks(callback, db, config)
    await callback.answer("Время открыто" if deleted else "Это время уже открыто")
