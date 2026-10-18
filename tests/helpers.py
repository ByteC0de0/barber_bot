"""Фейковый Telegram для тестов: апдейты подаются в диспетчер напрямую,
а все запросы бота к API записываются в список вместо отправки в сеть."""

import asyncio
import functools
import itertools
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.filters.callback_data import CallbackData
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)

from bot.config import Config
from bot.database import Database
from bot.handlers import get_routers

CLIENT = User(id=1, is_bot=False, first_name="Иван", username="ivan")
OTHER = User(id=2, is_bot=False, first_name="Пётр")

# Роутер можно подключить только к одному диспетчеру, поэтому он общий на все тесты,
# а config и db передаются в каждый апдейт отдельно.
DP = Dispatcher()
DP.include_routers(*get_routers())


def async_test(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []
        self._message_ids = itertools.count(100)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(
                message_id=next(self._message_ids),
                date=datetime.now(),
                chat=Chat(id=method.chat_id or 0, type="private"),
                text=method.text,
            )
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""


class Harness:
    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db
        self.session = FakeSession()
        self.bot = Bot(
            "123456:TEST",
            session=self.session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._ids = itertools.count(1)

    async def _feed(self, **kwargs) -> None:
        update = Update(update_id=next(self._ids), **kwargs)
        await DP.feed_update(self.bot, update, config=self.config, db=self.db)

    async def send(self, user: User, text: str) -> None:
        message = Message(
            message_id=next(self._ids),
            date=datetime.now(),
            chat=Chat(id=user.id, type="private"),
            from_user=user,
            text=text,
        )
        await self._feed(message=message)

    async def click(self, user: User, data: str | CallbackData) -> None:
        if isinstance(data, CallbackData):
            data = data.pack()
        callback = CallbackQuery(
            id=str(next(self._ids)),
            from_user=user,
            chat_instance="test",
            data=data,
            message=Message(
                message_id=next(self._ids),
                date=datetime.now(),
                chat=Chat(id=user.id, type="private"),
                text="...",
            ),
        )
        await self._feed(callback_query=callback)

    async def click_button(self, user: User, text_part: str) -> None:
        for button in self.buttons(user.id):
            if text_part in button.text:
                await self.click(user, button.callback_data)
                return
        texts = [b.text for b in self.buttons(user.id)]
        raise AssertionError(f"Нет кнопки с «{text_part}». Есть: {texts}")

    def messages(self, chat_id: int) -> list[SendMessage | EditMessageText]:
        return [
            call
            for call in self.session.calls
            if isinstance(call, (SendMessage, EditMessageText)) and call.chat_id == chat_id
        ]

    def last(self, chat_id: int) -> SendMessage | EditMessageText:
        return self.messages(chat_id)[-1]

    def buttons(self, chat_id: int) -> list[InlineKeyboardButton]:
        for call in reversed(self.messages(chat_id)):
            if isinstance(call.reply_markup, InlineKeyboardMarkup):
                return [b for row in call.reply_markup.inline_keyboard for b in row]
        return []

    def button_texts(self, chat_id: int) -> list[str]:
        return [b.text for b in self.buttons(chat_id)]

    def last_alert(self) -> str | None:
        for call in reversed(self.session.calls):
            if isinstance(call, AnswerCallbackQuery) and call.show_alert:
                return call.text
        return None
