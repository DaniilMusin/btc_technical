import asyncio
import importlib
import os
import sys
import types

import pandas as pd


class DummyTg:
    async def start(self):
        pass

    async def stop(self):
        pass

    async def notify(self, *a, **k):
        pass


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

sys.modules.setdefault("services.telegram_bot", types.ModuleType("services.telegram_bot")).TgNotifier = DummyTg

trader = importlib.import_module("core.trader")
strategy = importlib.import_module("core.strategy")


def test_run_once_records_trade(monkeypatch):
    os.environ["USE_TESTNET"] = "true"
    lt = trader.LiveTrader("BTCUSDT", "1m")

    times = pd.date_range("2024-01-01", periods=3, freq="1min")
    df = pd.DataFrame(
        {
            "Open": [100, 101, 102],
            "High": [101, 102, 103],
            "Low": [99, 100, 101],
            "Close": [101, 102, 103],
            "Volume": [1, 1, 1],
        },
        index=times,
    )

    async def fake_fetch_history():
        return df

    monkeypatch.setattr(lt.feed, "fetch_history", fake_fetch_history, raising=False)

    lt.strategy.side = "LONG"
    lt.strategy.qty = 1.0
    lt.strategy.entry = 100.0

    monkeypatch.setattr(lt.strategy, "on_new_candle", lambda d: {"action": "EXIT"})

    async def dummy_place_market(*a, **k):
        return {"price": 110}

    monkeypatch.setattr(lt.broker, "place_market", dummy_place_market)

    trades: list[dict] = []

    def fake_store_trade(**kw):
        trades.append(kw)
        return types.SimpleNamespace(**kw)

    monkeypatch.setattr(strategy, "store_trade", fake_store_trade)

    async def runner():
        await lt.run_once()

    asyncio.run(runner())

    assert len(trades) >= 1

