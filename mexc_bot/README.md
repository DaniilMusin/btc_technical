# Mexc Bot

Проект предназначен для запуска адаптивного торгового бота на бирже MEXC. Он
поддерживает режим тестовой торговли, уведомления в Telegram и ведение простой
статистики сделок в SQLite.

## Быстрый старт

```bash
cp .env.example .env
# заполните реальные ключи

docker compose up --build -d
```

При `USE_TESTNET=true` ордера не отправляются на биржу. Чтобы дополнительно
сохранять свечи в архив `data/ohlc_archive.csv`, выставьте `ARCHIVE_CSV=true` в
`.env`.
`.env`. Архив очищается автоматически, храня данные лишь за последние три
месяца (переменная `HISTORY_MONTHS` в `.env`).

## Tested with Python 3.11 / 3.10

`mexc-sdk-python` публикуется с ограничением `<3.12`, поэтому под Python 3.12 зависимость пропускается и проект не собирается.
Используйте Python **3.11** (или 3.10) в отдельном виртуальном окружении. Ниже пример настройки с помощью `pyenv`:

```bash
pyenv install 3.11.12
pyenv local 3.11.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dockerfile и `docker-compose.yml` уже используют образ Python 3.11.

## Backtest

Стратегия протестирована на наборе данных `btc_1d_data_2018_to_2025.csv`. Результаты
подтвердили корректность работы `run_backtest()` и всего проекта в целом.

## Telegram notifications

Создайте бота через `@BotFather` и запишите `TG_BOT_TOKEN` и `TG_CHAT_ID` в `.env`. Файл `telegram_utils.py` содержит функцию `tg_send()` для отправки сообщений без тяжёлых зависимостей:

```python
from telegram_utils import tg_send

tg_send("Test OK ✅")
```

В стратегию добавлены методы `_notify_trade_open` и `_notify_trade_close`, вызываемые при открытии и закрытии позиции. Если переменные окружения заданы, бот пришлёт уведомления прямо в Telegram.

## Troubleshooting

### 1. Package `mexc-sdk-python` fails to install

The official SDK on PyPI declares compatibility only up to Python 3.11. If you attempt to install it under Python 3.12, `pip` skips the dependency. Use one of the following approaches:

- **Recommended:** run the bot under Python 3.11. The provided Dockerfile already uses `python:3.11-slim`.
- **Alternative:** install the SDK directly from GitHub (`pip install "git+https://github.com/mexc-dev/mexc-sdk-python@master"`).
- **Last resort:** ignore the Python requirement with `pip install mexc-sdk-python==1.4.2 --break-system-packages` (may break in future).

### 2. `run_backtest()` returns an empty DataFrame

Check the input CSV:

1. Ensure the file path is correct and the file has at least 200‑300 rows.
2. Columns must include `Open`, `High`, `Low`, `Close` and `Volume` (any case).
3. After loading the data you can call `strategy.validate_data()` to verify column names.
4. Replace zero or empty cells with `NaN` before running `calculate_indicators()`.

```python
strategy.load_data()
strategy.validate_data()
strategy.calculate_indicators()
print(strategy.data.isna().sum())
```

These checks usually reveal why the backtest produced no trades.
