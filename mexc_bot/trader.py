"""Compatibility wrapper – imports actual LiveTrader from core.trader."""
from core.trader import LiveTrader as _CoreLiveTrader

__all__ = ["LiveTrader"]


class LiveTrader(_CoreLiveTrader):
    """Alias for backward compatibility."""
    pass
