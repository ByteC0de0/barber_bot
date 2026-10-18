"""Точка входа: создаём бота, подключаем обработчики и запускаем."""

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.config import Config, load_config
from bot.database import Database
from bot.handlers import get_routers
from bot.reminders import reminder_loop

logger = logging.getLogger("bot")

CLIENT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="book", description="Записаться"),
    BotCommand(command="my", description="Мои записи"),
    BotCommand(command="prices", description="Услуги и цены"),
]
ADMIN_COMMANDS = CLIENT_COMMANDS + [BotCommand(command="admin", description="Админ-панель")]


async def set_commands(bot: Bot, config: Config) -> None:
    """Меню команд (кнопка «/» в Telegram). Админам — с пунктом «Админ-панель»."""
    try:
        await bot.set_my_commands(CLIENT_COMMANDS)
    except TelegramAPIError as e:
        # Без меню команд бот всё равно работает — не падаем из-за сбоя сети при старте
        logger.warning("Не удалось задать меню команд: %s", e)
        return
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as e:
            logger.warning("Не удалось задать команды админу %s (он писал боту?): %s", admin_id, e)


async def wait_for_telegram(bot: Bot, first_delay: float = 5, max_delay: float = 60) -> None:
    """Ждёт, пока Telegram станет доступен. Без этого aiogram падает на старте,
    если в момент запуска пропала сеть. Ответ кэшируется в bot.me()."""
    delay = first_delay
    while True:
        try:
            me = await bot.me()
            logger.info("Связь с Telegram есть: @%s", me.username)
            return
        except TelegramNetworkError as e:
            logger.warning("Нет связи с Telegram (%s). Повтор через %s с", e, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def on_startup(bot: Bot, dispatcher: Dispatcher, config: Config, db: Database) -> None:
    await set_commands(bot, config)
    if not config.admin_ids:
        logger.warning("ADMIN_IDS не задан — уведомления мастеру отправляться не будут")
    if config.reminder_hours:
        dispatcher["reminder_task"] = asyncio.create_task(reminder_loop(bot, db, config))


async def on_shutdown(dispatcher: Dispatcher) -> None:
    task = dispatcher.workflow_data.get("reminder_task")
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    config = load_config()
    db = Database(config.db_path)
    await db.init()
    logger.info("База: %s", config.db_path)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # Всё, что передано в Dispatcher(...), aiogram подставит в обработчики по имени
    # аргумента: def handler(message, db: Database, config: Config)
    dp = Dispatcher(config=config, db=db)
    dp.include_routers(*get_routers())
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await wait_for_telegram(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
