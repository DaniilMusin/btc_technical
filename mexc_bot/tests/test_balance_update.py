import importlib
import pandas as pd
import asyncio
import os
import sys
import types

class DummyTg:
    async def start(self):
        pass

    async def stop(self):
        pass

    async def notify(self, *a, **k):
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

# stub external deps not needed for the test
sys.modules.setdefault("services.telegram_bot", types.ModuleType("services.telegram_bot")).TgNotifier = DummyTg

trader = importlib.import_module('core.trader')
strategy = importlib.import_module('core.strategy')

class DummyTrade:
    def __init__(self, pnl):
        self.pnl = pnl

async def dummy_notify(*a, **k):
    pass

async def dummy_place_market(symbol, side, qty):
    return {"price": 110}


def test_balance_updates_on_close(monkeypatch):
    lt = trader.LiveTrader('BTCUSDT', '1m')
    assert isinstance(lt.feed, trader.StreamingDataFeed)
    lt.strategy.side = 'LONG'
    lt.strategy.qty = 1.0
    lt.strategy.entry = 100.0

    monkeypatch.setattr(lt.strategy, 'on_new_candle', lambda df: {'action': 'EXIT'})
    monkeypatch.setattr(strategy, 'store_trade', lambda **kw: DummyTrade(kw['pnl']))
    monkeypatch.setattr(lt.broker, 'place_market', dummy_place_market)
    monkeypatch.setattr(lt.tg, 'notify', dummy_notify)

    df = pd.DataFrame({'Close': [110]}, index=[pd.Timestamp('2024-01-01')])
    start_balance = lt.balance
    asyncio.run(lt.on_candle(df))
    assert lt.balance == start_balance + 10
