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

## Tested with Python 3.11 / 3.10

Библиотека `mexc-sdk-python` в текущей версии не устанавливается под Python 3.12. 
Рекомендуется использовать Python 3.11 (или 3.10) и отдельное виртуальное окружение. 
Ниже пример настройки с помощью `pyenv`:

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
