import sys
import os
import types

import core.strategy as strategy
=======
import importlib


# Stub heavy matplotlib modules
mpl = types.ModuleType("matplotlib")
mpl.pyplot = types.ModuleType("pyplot")
mpl.dates = types.ModuleType("dates")
mpl.ticker = types.ModuleType("ticker")
mpl.ticker.FuncFormatter = lambda *a, **k: None
sys.modules.setdefault("matplotlib", mpl)
sys.modules.setdefault("matplotlib.pyplot", mpl.pyplot)
sys.modules.setdefault("matplotlib.dates", mpl.dates)
sys.modules.setdefault("matplotlib.ticker", mpl.ticker)

# Ensure project root is on path so `core` package resolves
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


BalancedAdaptiveStrategyLive = strategy.BalancedAdaptiveStrategyLive


def test_calc_qty_price_equals_sl(monkeypatch):
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")
    db = importlib.import_module("core.db")
    importlib.reload(db)
    strategy = importlib.import_module("core.strategy")
    importlib.reload(strategy)
    monkeypatch.setattr(strategy, "last_n_pnl", lambda n=20: [])
    BalancedAdaptiveStrategyLive = strategy.BalancedAdaptiveStrategyLive
    strat = BalancedAdaptiveStrategyLive()
    qty = strat.calc_qty(balance=1000, price=100.0, sl=100.0)
    assert qty > 0
