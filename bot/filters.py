from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.config import Config


class IsAdmin(BaseFilter):
    """Пропускает только пользователей из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject, config: Config) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and config.is_admin(user.id)
