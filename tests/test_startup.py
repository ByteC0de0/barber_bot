from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe
from aiogram.types import User

from main import wait_for_telegram
from tests.helpers import FakeSession, Harness, async_test


class FlakySession(FakeSession):
    """Первые несколько запросов падают с сетевой ошибкой, потом всё работает."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if self.failures:
            self.failures -= 1
            raise TelegramNetworkError(method=method, message="нет сети")
        return User(id=123456, is_bot=True, first_name="Тест", username="test_bot")


@async_test
async def test_wait_for_telegram_retries_until_network_is_back(config, db):
    h = Harness(config, db)
    h.bot.session = FlakySession(failures=3)
    await wait_for_telegram(h.bot, first_delay=0)
    assert (await h.bot.me()).username == "test_bot"
    assert sum(isinstance(c, GetMe) for c in h.bot.session.calls) == 4
