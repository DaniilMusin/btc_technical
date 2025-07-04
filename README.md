# BingX Bot

Проект предназначен для запуска адаптивного торгового бота на бирже BingX. Он
поддерживает режим тестовой торговли, уведомления в Telegram и ведение простой
статистики сделок в SQLite.

## Быстрый старт

```bash
cp .env.example .env  # пример расположен в корне проекта
# заполните реальные ключи

docker compose up --build -d
```

При `USE_TESTNET=true` ордера не отправляются на биржу. Для BingX можно также
задать `BINGX_TESTNET=true` — это внутренний алиас `USE_TESTNET`, включающий
dry-run режим. Чтобы дополнительно сохранять свечи в архив `data/ohlc_archive.csv`,
выставьте `ARCHIVE_CSV=true` в `.env`.
Для фьючерсных ордеров BingX поддерживаются переменные `BINGX_MARGIN_MODE` и
`BINGX_LEVERAGE`. По умолчанию используется изолированная маржа и плечо 3x.

## Tested with Python 3.11 / 3.10

Рекомендуется использовать Python 3.11 (или 3.10) и отдельное виртуальное окружение.
Ниже пример настройки с помощью `pyenv`:

```bash
pyenv install 3.11.12
pyenv local 3.11.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install .[mexc]    # требуется для поддержки MEXC
```

Dockerfile и `docker-compose.yml` уже используют образ Python 3.11.

## Local workflow

Для разработки рекомендуется отдельное окружение:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

Так можно локально повторить шаги CI.

## Backtest

Стратегия протестирована на наборе данных `btc_1d_data_2018_to_2025.csv`. Результаты
подтвердили корректность работы `run_backtest()` и всего проекта в целом.

## Комиссия

Комиссии на вход и выход рассчитываются отдельно.
При открытии позиции баланс уменьшается на `position_size * SINGLE_SIDE_FEE`.
При закрытии комиссия берётся как `position_size * exit_price * SINGLE_SIDE_FEE` и
вычитается из расчёта PnL. Оба коэффициента по умолчанию равны `0.00035`,
что в сумме соответствует прежнему уровню 0.07% за полный круг.
Значение комиссии задаётся в `mexc_bot.core.broker` и используется в стратегии и при бэктестах.

## Telegram notifications

Создайте бота через `@BotFather` и запишите `TG_BOT_TOKEN` и `TG_CHAT_ID` в `.env`. Файл `telegram_utils.py` содержит функцию `tg_send()` для отправки сообщений без тяжёлых зависимостей:

```python
from telegram_utils import tg_send

tg_send("Test OK ✅")
```

В стратегию добавлены методы `_notify_trade_open` и `_notify_trade_close`, вызываемые при открытии и закрытии позиции. Если переменные окружения заданы, бот пришлёт уведомления прямо в Telegram.

## Pre-commit

Файл `.pre-commit-config.yaml` задаёт основные хуки `black`, `ruff`, `mypy` и `pytest`.
Для автоматического форматирования кода и запуска статических проверок
установите `pre-commit` и активируйте их:

```bash
pip install pre-commit
pre-commit install
```

После установки хуки будут выполняться при каждом коммите.
Для ручового запуска на всём проекте используйте:

```bash
pre-commit run --all-files
```
