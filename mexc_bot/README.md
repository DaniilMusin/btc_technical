# Mexc Bot

Проект предназначен для запуска адаптивного торгового бота на бирже MEXC. Он
поддерживает режим тестовой торговли, уведомления в Telegram и ведение простой
статистики сделок в SQLite.

> **Note**: Бот использует собственное подключение к WebSocket API MEXC, поэтому
> дополнительных SDK не требуется. Для совместимости используйте Python 3.11
> (или 3.10).

## Быстрый старт

```bash
cp .env.example .env
# заполните реальные ключи

docker compose up --build -d
```

При `USE_TESTNET=true` ордера не отправляются на биржу. Чтобы дополнительно
сохранять свечи в архив `data/ohlc_archive.csv`, выставьте `ARCHIVE_CSV=true` в

`.env`. Архив очищается автоматически, храня данные лишь за последние три
месяца (переменная `HISTORY_MONTHS` в `.env`).

## Tested with Python 3.11 / 3.10


Используйте Python **3.11** (или 3.10) в отдельном виртуальном окружении. Ниже
пример настройки с помощью `pyenv`:


```bash
pyenv install 3.11.12
pyenv local 3.11.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dockerfile и `docker-compose.yml` уже используют образ Python 3.11.

## Backtest


Для проверки стратегии требуется CSV со свечами. Файл `btc_1d_data_2018_to_2025.csv`
удалён из репозитория, поэтому используйте собственный набор данных или
скачайте аналогичный исторический файл.

## Telegram notifications

Создайте бота через `@BotFather` и запишите `TG_BOT_TOKEN` и `TG_CHAT_ID` в `.env`.
Файл `telegram_utils.py` содержит функцию `tg_send()` для отправки сообщений без
тяжёлых зависимостей:


```python
from telegram_utils import tg_send

tg_send("Test OK ✅")
```


В стратегию добавлены методы `_notify_trade_open` и `_notify_trade_close`,
вызываемые при открытии и закрытии позиции. Если переменные окружения заданы,
бот пришлёт уведомления прямо в Telegram.


## Configuration

Параметры торговой стратегии задаются в `config.yml`.
Пример файла:

```yaml
symbol: ${DEFAULT_SYMBOL}
interval: ${DEFAULT_INTERVAL}

risk:
  initial_balance: ${INITIAL_BALANCE}
  max_leverage: 3
  base_risk_per_trade: 0.02
  min_trades_interval: 6
```

Значения вида `${VAR}` подставляются из вашего `.env` файла.

## Troubleshooting


### `run_backtest()` returns an empty DataFrame


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


## FAQ

### How do I make sure Python 3.11 is used instead of the system Python?

If you have several Python versions installed, `pyenv` helps manage them.
Run the commands below once in the project directory:

```bash
pyenv install 3.11.12   # skip if already installed
pyenv local 3.11.12
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `.python-version` file pins the interpreter to 3.11.12 so that
`pyenv` automatically selects it and avoids using the system Python.

