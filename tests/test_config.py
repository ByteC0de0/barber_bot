from datetime import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.config import BASE_DIR, Config, load_config


def env_config(monkeypatch, tmp_path, **env) -> Config:
    """Конфиг из переменных окружения, как при чтении .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(f"{k}={v}" for k, v in env.items()), encoding="utf-8")
    return Config(_env_file=env_file)


def test_values_from_env_are_parsed(monkeypatch, tmp_path):
    config = env_config(
        monkeypatch,
        tmp_path,
        BOT_TOKEN="123:abc-DEF",
        ADMIN_IDS="5, 7",
        WORK_START="09:30",
        REMINDER_HOURS="2,24,2",
        DB_PATH="data/x.db",
    )
    assert config.admin_ids == (5, 7)
    assert config.work_start == time(9, 30)
    assert config.reminder_hours == (24, 2)  # без дублей, по убыванию
    assert config.db_path == BASE_DIR / Path("data/x.db")
    assert config.is_admin(7) and not config.is_admin(1)


def test_empty_admin_ids_allowed(monkeypatch, tmp_path):
    assert env_config(monkeypatch, tmp_path, BOT_TOKEN="1:a", ADMIN_IDS="").admin_ids == ()


@pytest.mark.parametrize(
    "env",
    [
        {"BOT_TOKEN": ""},
        {"BOT_TOKEN": "не токен"},
        {"BOT_TOKEN": "1:a", "ADMIN_IDS": "abc"},
        {"BOT_TOKEN": "1:a", "WORK_START": "20:00", "WORK_END": "10:00"},
        {"BOT_TOKEN": "1:a", "WORK_START": "25:00"},
        {"BOT_TOKEN": "1:a", "SLOT_STEP": "0"},
        {"BOT_TOKEN": "1:a", "TIMEZONE": "Mars/Olympus"},
        {"BOT_TOKEN": "1:a", "REMINDER_HOURS": "0"},
        {"BOT_TOKEN": "1:a", "DAYS_AHEAD": "-1"},
    ],
)
def test_invalid_values_rejected(monkeypatch, tmp_path, env):
    with pytest.raises(ValidationError):
        env_config(monkeypatch, tmp_path, **env)


def test_load_config_explains_error(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "1:a")
    monkeypatch.setenv("SLOT_STEP", "abc")
    with pytest.raises(RuntimeError, match="SLOT_STEP"):
        load_config()
