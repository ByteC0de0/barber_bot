# Бот записи в барбершоп / салон красоты

Telegram-бот, через который клиенты сами записываются на услуги, а мастер видит расписание и управляет рабочим временем. Демо: [@bytecodebarberbot](https://t.me/bytecodebarberbot).

**Стек:** Python 3.12 · aiogram 3 · SQLite (aiosqlite) · pytest

## Возможности

**Клиент**
- Записаться в 4 шага: услуга (цена и длительность) → дата → свободное время → подтверждение.
- Видит только реально свободное время: занятое, закрытое мастером и прошедшее не показывается. Учитывается длительность услуги: 90-минутную стрижку нельзя поставить за 30 минут до закрытия.
- «Мои записи»: список предстоящих визитов и отмена в два нажатия.
- Напоминания за 24 часа и за 2 часа до визита (настраивается), с кнопкой отмены.
- Прайс-лист.

**Мастер / админ**
- Уведомления о новых записях и отменах со ссылкой на клиента.
- Записи на сегодня или на любой день, с суммой выручки за день.
- Отмена записи клиента, клиент получает уведомление.
- Закрыть время: весь день (выходной) или промежуток (перерыв). Открыть закрытое время обратно.
- Если на закрываемое время уже есть записи, бот предупредит и ничего не закроет.

**Надёжность**
- Двое клиентов одновременно нажали «Подтвердить» на одно время: запишется только первый (транзакция `BEGIN IMMEDIATE` в SQLite).
- Время проверяется заново при подтверждении: устаревшая кнопка не даст записаться на занятое или прошедшее время.
- Отправленные напоминания хранятся в базе, поэтому после перезапуска бота они не дублируются. Если бот был выключен и пропустил несколько напоминаний, клиенту придёт одно.
- Лимит активных записей на одного клиента (по умолчанию 3).

## Структура

```
barber_bot/
├── main.py                 # запуск: бот, диспетчер, меню команд, фоновые напоминания
├── bot/
│   ├── config.py           # настройки из .env
│   ├── database.py         # SQLite: услуги, записи, закрытое время, напоминания
│   ├── scheduling.py       # расчёт свободных слотов
│   ├── reminders.py        # фоновая задача напоминаний
│   ├── callbacks.py        # данные inline-кнопок
│   ├── formatting.py       # даты, цены, карточки записей
│   ├── messaging.py        # безопасная отправка/редактирование сообщений
│   ├── filters.py          # фильтр «только админ»
│   ├── keyboards/          # клавиатуры клиента и админа
│   └── handlers/           # обработчики: common, booking, my_bookings, admin, fallback
├── tests/                  # тесты логики и сценариев целиком (фейковый Telegram)
├── deploy/barber-bot.service  # unit-файл systemd для сервера
├── Dockerfile, docker-compose.yml
├── requirements.txt, requirements-dev.txt
└── .env.example            # образец настроек
```

## Запуск локально

1. Создать бота у [@BotFather](https://t.me/BotFather) и получить токен.
2. Установить зависимости:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # Linux / macOS
   pip install -r requirements.txt
   ```

3. Скопировать `.env.example` в `.env` и вписать `BOT_TOKEN`. Свой Telegram ID можно узнать командой `/id` в боте. Его нужно вписать в `ADMIN_IDS` и перезапустить бота.
4. Запустить:

   ```bash
   python main.py
   ```

База `data/bot.db` и демо-услуги создаются автоматически при первом запуске.

> Одним токеном может пользоваться только один запущенный бот. Если бот уже работает на сервере, локальную копию с тем же токеном запускать нельзя: Telegram вернёт ошибку `Conflict`.

## Настройки (.env)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `BOT_TOKEN` | — | Токен от @BotFather (обязательно) |
| `ADMIN_IDS` | — | Telegram ID мастеров через запятую |
| `SALON_NAME` | Барбершоп «Демо» | Название в сообщениях |
| `TIMEZONE` | Europe/Moscow | Часовой пояс салона |
| `WORK_START` / `WORK_END` | 10:00 / 20:00 | Часы работы |
| `SLOT_STEP` | 30 | Шаг сетки записи, минут |
| `DAYS_AHEAD` | 14 | На сколько дней вперёд открыта запись |
| `REMINDER_HOURS` | 24,2 | За сколько часов напоминать |
| `MAX_ACTIVE_BOOKINGS` | 3 | Максимум активных записей у клиента |
| `DB_PATH` | data/bot.db | Путь к базе |

Услуги задаются в `DEFAULT_SERVICES` в [bot/database.py](bot/database.py) и создаются при первом запуске. Если база уже есть, услуги меняют прямо в таблице `services`, например через DB Browser for SQLite.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Тесты проходят сценарии целиком так, будто пользователь нажимает кнопки: запись, гонку двух клиентов за одно время, отмену, выходной и перерыв, права админа, напоминания. Запросы к Telegram подменены, сеть не нужна.

## Запуск на сервере (24/7)

Подойдёт любой VPS с Ubuntu 24.04 (в ней Python 3.12; ресурсов хватит минимальных: 1 vCPU / 512 МБ). Нужен сервер, с которого доступен `api.telegram.org`.

### Вариант 1: systemd

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
sudo git clone https://github.com/<ваш-логин>/barber_bot.git /opt/barber_bot
cd /opt/barber_bot
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env
sudo nano .env                                 # вписать BOT_TOKEN и ADMIN_IDS
sudo useradd --system --no-create-home botuser # бот работает не от root
sudo chown -R botuser:botuser /opt/barber_bot
sudo chmod 600 .env
sudo cp deploy/barber-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now barber-bot
```

- Логи: `journalctl -u barber-bot -f`
- Перезапуск: `sudo systemctl restart barber-bot`
- Обновление: `cd /opt/barber_bot && sudo -u botuser git pull && sudo systemctl restart barber-bot`

systemd сам перезапустит бота, если тот упадёт, и запустит его после перезагрузки сервера.

### Вариант 2: Docker

```bash
cp .env.example .env    # вписать BOT_TOKEN и ADMIN_IDS
docker compose up -d --build
docker compose logs -f
```

База хранится в папке `./data` на хосте и переживает пересборку контейнера.

### Бэкап базы

Вся информация лежит в одном файле `data/bot.db`. Копию можно делать по cron, например так: `sqlite3 data/bot.db ".backup backup.db"`.

## Идеи для развития

- Несколько мастеров с собственным расписанием.
- Управление услугами и часами работы прямо из админ-панели.
- Запрос номера телефона клиента.
- Экспорт записей в Google Sheets.
- Онлайн-предоплата через Telegram Payments.
