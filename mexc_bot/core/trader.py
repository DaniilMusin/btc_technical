from importlib import import_module

mod = import_module('mexc_bot.trader')
LiveTrader = mod.LiveTrader
StreamingDataFeed = mod.StreamingDataFeed if hasattr(mod, 'StreamingDataFeed') else None

__all__ = ['LiveTrader', 'StreamingDataFeed']
