"""Сценарии целиком: как если бы пользователь нажимал кнопки в Telegram."""

from datetime import datetime, time, timedelta

from aiogram.types import ReplyKeyboardMarkup, User

from bot.callbacks import AdminCb, ConfirmCb, SlotCb, pack_dt
from bot.formatting import day_short
from bot.keyboards.client import BTN_ADMIN, BTN_BOOK, BTN_MY
from tests.conftest import ADMIN_ID, make_config
from tests.helpers import CLIENT, OTHER, Harness, async_test

ADMIN = User(id=ADMIN_ID, is_bot=False, first_name="Мастер")


def tomorrow(config):
    return config.now().date() + timedelta(days=1)


async def book(h: Harness, user: User, service: str, day, hhmm: str) -> None:
    await h.send(user, BTN_BOOK)
    await h.click_button(user, service)
    await h.click_button(user, day_short(day))
    await h.click_button(user, hhmm)
    await h.click_button(user, "Подтвердить")


def reply_buttons(call) -> list[str]:
    assert isinstance(call.reply_markup, ReplyKeyboardMarkup)
    return [b.text for row in call.reply_markup.keyboard for b in row]


@async_test
async def test_start_menu_for_client_and_admin(config, db):
    h = Harness(config, db)
    await h.send(CLIENT, "/start")
    assert BTN_ADMIN not in reply_buttons(h.last(CLIENT.id))
    await h.send(ADMIN, "/start")
    assert BTN_ADMIN in reply_buttons(h.last(ADMIN_ID))


@async_test
async def test_client_books_and_admin_notified(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await h.send(CLIENT, BTN_BOOK)
    await h.click_button(CLIENT, "Мужская стрижка")
    await h.click_button(CLIENT, day_short(day))
    await h.click_button(CLIENT, "10:00")
    assert "Проверьте запись" in h.last(CLIENT.id).text
    await h.click_button(CLIENT, "Подтвердить")

    assert "Вы записаны" in h.last(CLIENT.id).text
    [booking] = await db.get_user_upcoming(CLIENT.id, config.now())
    assert booking.start == datetime.combine(day, time(10))
    assert booking.client_username == "ivan"
    assert "Новая запись" in h.last(ADMIN_ID).text


@async_test
async def test_taken_time_not_offered(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await book(h, CLIENT, "Мужская стрижка", day, "10:00")  # 10:00–11:00

    await h.send(OTHER, BTN_BOOK)
    await h.click_button(OTHER, "Стрижка машинкой")
    await h.click_button(OTHER, day_short(day))
    times = h.button_texts(OTHER.id)
    assert "10:00" not in times and "10:30" not in times
    assert "11:00" in times


@async_test
async def test_two_clients_same_slot_only_first_wins(config, db):
    h = Harness(config, db)
    start = datetime.combine(tomorrow(config), time(12))
    confirm = ConfirmCb(service_id=1, at=pack_dt(start))
    await h.click(CLIENT, confirm)
    await h.click(OTHER, confirm)

    assert "уже занято" in h.last_alert()
    assert len(await db.get_day_bookings(start.date())) == 1
    assert await db.get_user_upcoming(OTHER.id, config.now()) == []


@async_test
async def test_past_and_off_hours_time_rejected(config, db):
    h = Harness(config, db)
    past = config.now().replace(minute=0) - timedelta(hours=1)
    night = datetime.combine(tomorrow(config), time(3))
    for start, message in ((past, "уже прошло"), (night, "Салон работает")):
        await h.click(CLIENT, ConfirmCb(service_id=1, at=pack_dt(start)))
        assert message in h.last_alert()
    assert await db.get_user_upcoming(CLIENT.id, config.now() - timedelta(days=1)) == []


@async_test
async def test_no_confirm_button_for_taken_time(config, db):
    h = Harness(config, db)
    start = datetime.combine(tomorrow(config), time(12))
    await h.click(CLIENT, ConfirmCb(service_id=1, at=pack_dt(start)))  # CLIENT занял 12:00

    # OTHER открыл экран подтверждения со старой кнопкой времени 12:00
    await h.click(OTHER, SlotCb(service_id=1, at=pack_dt(start)))
    assert "уже занято" in h.last_alert()
    assert not any("Подтвердить" in t for t in h.button_texts(OTHER.id))
    assert "12:00" not in h.button_texts(OTHER.id)  # показан актуальный список времени


@async_test
async def test_confirm_screen_shows_all_details(config, db):
    h = Harness(config, db)
    await h.send(CLIENT, BTN_BOOK)
    await h.click_button(CLIENT, "Мужская стрижка")
    await h.click_button(CLIENT, day_short(tomorrow(config)))
    await h.click_button(CLIENT, "10:00")
    text = h.last(CLIENT.id).text
    for part in ("Мужская стрижка", "10:00–11:00", "1 500 ₽", "Иван"):
        assert part in text
    assert any("Подтвердить" in t for t in h.button_texts(CLIENT.id))


@async_test
async def test_forged_callback_goes_to_fallback(config, db):
    h = Harness(config, db)
    await h.click(CLIENT, "ok:1:203099999999")
    assert "устарела" in h.last_alert()
    assert await db.get_user_upcoming(CLIENT.id, config.now()) == []


@async_test
async def test_admin_invalid_break_rejected(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    start = datetime.combine(day, time(15))
    end = datetime.combine(day, time(14))
    await h.click(ADMIN, AdminCb(action="block_to", start=pack_dt(start), end=pack_dt(end)))
    assert "позже начала" in h.last_alert()
    assert await db.get_day_blocks(day) == []


@async_test
async def test_booking_limit(tmp_path, db):
    config = make_config(tmp_path, max_active_bookings=1)
    h = Harness(config, db)
    await book(h, CLIENT, "Мужская стрижка", tomorrow(config), "10:00")
    await h.send(CLIENT, BTN_BOOK)
    assert "максимум" in h.last(CLIENT.id).text


@async_test
async def test_client_cancels_booking(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await book(h, CLIENT, "Мужская стрижка", day, "10:00")

    await h.send(CLIENT, BTN_MY)
    assert "Мужская стрижка" in h.last(CLIENT.id).text
    await h.click_button(CLIENT, "Отменить")
    await h.click_button(CLIENT, "Да, отменить")

    assert "Запись отменена" in h.last(CLIENT.id).text
    assert await db.get_user_upcoming(CLIENT.id, config.now()) == []
    assert "Клиент отменил запись" in h.last(ADMIN_ID).text

    # Время снова свободно
    await h.send(OTHER, BTN_BOOK)
    await h.click_button(OTHER, "Мужская стрижка")
    await h.click_button(OTHER, day_short(day))
    assert "10:00" in h.button_texts(OTHER.id)


@async_test
async def test_cannot_cancel_someone_elses_booking(config, db):
    h = Harness(config, db)
    await book(h, CLIENT, "Мужская стрижка", tomorrow(config), "10:00")
    [booking] = await db.get_user_upcoming(CLIENT.id, config.now())

    from bot.callbacks import MyCb

    await h.click(OTHER, MyCb(action="cancel", booking_id=booking.id))
    assert "уже отменена или прошла" in h.last_alert()
    assert (await db.get_booking(booking.id)).status == "active"


@async_test
async def test_admin_day_off_hides_day(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await h.send(ADMIN, BTN_ADMIN)
    await h.click_button(ADMIN, "Закрыть время")
    await h.click_button(ADMIN, day_short(day))
    await h.click_button(ADMIN, "Весь день")
    assert "Время закрыто" in h.last(ADMIN_ID).text

    await h.send(CLIENT, BTN_BOOK)
    await h.click_button(CLIENT, "Мужская стрижка")
    assert day_short(day) not in h.button_texts(CLIENT.id)


@async_test
async def test_admin_break_and_reopen(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await h.send(ADMIN, BTN_ADMIN)
    await h.click_button(ADMIN, "Закрыть время")
    await h.click_button(ADMIN, day_short(day))
    await h.click_button(ADMIN, "14:00")
    await h.click_button(ADMIN, "15:00")
    assert "Время закрыто" in h.last(ADMIN_ID).text

    async def client_times():
        await h.send(CLIENT, BTN_BOOK)
        await h.click_button(CLIENT, "Стрижка машинкой")
        await h.click_button(CLIENT, day_short(day))
        return h.button_texts(CLIENT.id)

    times = await client_times()
    assert "14:00" not in times and "14:30" not in times
    assert "13:30" in times and "15:00" in times

    await h.click(ADMIN, AdminCb(action="blocks"))
    await h.click_button(ADMIN, "14:00–15:00")
    assert "Закрытого времени нет" in h.last(ADMIN_ID).text
    assert "14:00" in await client_times()


@async_test
async def test_admin_cannot_close_booked_time(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await book(h, CLIENT, "Мужская стрижка", day, "10:00")

    await h.send(ADMIN, BTN_ADMIN)
    await h.click_button(ADMIN, "Закрыть время")
    await h.click_button(ADMIN, day_short(day))
    await h.click_button(ADMIN, "Весь день")
    assert "Нельзя закрыть" in h.last(ADMIN_ID).text
    assert await db.get_day_blocks(day) == []


@async_test
async def test_admin_sees_day_and_cancels_with_client_notice(config, db):
    h = Harness(config, db)
    day = tomorrow(config)
    await book(h, CLIENT, "Мужская стрижка", day, "10:00")

    await h.send(ADMIN, BTN_ADMIN)
    await h.click_button(ADMIN, "другой день")
    await h.click_button(ADMIN, day_short(day))
    text = h.last(ADMIN_ID).text
    assert "Мужская стрижка" in text and "Иван" in text and "1 500 ₽" in text

    await h.click_button(ADMIN, "❌ 10:00")
    await h.click_button(ADMIN, "Да, отменить")
    assert "отменена мастером" in h.last(CLIENT.id).text
    assert "Записей нет" in h.last(ADMIN_ID).text


@async_test
async def test_non_admin_has_no_access(config, db):
    h = Harness(config, db)
    await h.send(CLIENT, BTN_ADMIN)
    assert "Не понял" in h.last(CLIENT.id).text
    await h.click(CLIENT, AdminCb(action="blocks"))
    assert "устарела" in h.last_alert()
