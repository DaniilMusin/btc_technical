"""Trading helpers used by the CLI entrypoints and tests."""

from __future__ import annotations
import math
import os
from dotenv import load_dotenv
from loguru import logger

from .feed import StreamingDataFeed
from .broker import BingxBroker
from .strategy import BalancedAdaptiveStrategyLive
from .db import init_db
# Import notifier from the local services package so tests don't require
# modifying PYTHONPATH
try:
    # Tests stub ``services.telegram_bot`` in ``sys.modules`` so prefer that
    # when available. Fallback to the package-relative import when running the
    # application directly.
    from services.telegram_bot import TgNotifier  # type: ignore
except Exception:  # pragma: no cover
    from mexc_bot.services import telegram_bot as tgmod
    TgNotifier = tgmod.TgNotifier
    import sys
    sys.modules.setdefault("services.telegram_bot", tgmod)

load_dotenv()


class LiveTrader:
    """Simple wrapper that glues together feed, broker and strategy."""

    def __init__(self, symbol: str, interval: str, exchange: str = "BINGX"):
        # Валидация входных параметров
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if not interval or not isinstance(interval, str):
            raise ValueError("Interval must be a non-empty string")
        if interval not in ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]:
            logger.warning(f"Interval '{interval}' may not be supported by the exchange")
            
        self.symbol, self.interval = symbol.upper(), interval
        self.exchange = exchange.upper()
        self.testnet = os.getenv("USE_TESTNET", "true").lower() == "true"

        # modules
        self.feed = StreamingDataFeed(self.symbol, self.interval)
        if self.exchange != "BINGX":
            raise NotImplementedError(f"Exchange {self.exchange} is not supported")
        self.broker = BingxBroker(testnet=self.testnet, symbol=self.symbol)
        
        # Валидация initial_balance
        try:
            initial_balance = float(os.getenv("INITIAL_BALANCE", 1000))
            if initial_balance <= 0:
                raise ValueError("Initial balance must be positive")
        except (ValueError, TypeError):
            logger.error("Invalid INITIAL_BALANCE value, using default 1000")
            initial_balance = 1000
            
        self.strategy = BalancedAdaptiveStrategyLive(
            initial_balance=initial_balance
        )
        self.tg = TgNotifier()
        try:
            from services import telegram_bot as tgmod

            tgmod.trader = self
        except (ImportError, AttributeError) as e:
            logger.warning(f"Failed to set trader reference: {e}")
        except Exception as e:
            logger.error(f"Unexpected error setting trader reference: {e}")
        self.balance = initial_balance

    # ------------------------------------------------ #
    async def on_candle(self, df):
        ts = df.index[-1]  # время закрытия текущей свечи
        decision = self.strategy.on_new_candle(df)

        # ---------- OPEN ---------- #
        if decision["action"] in ("BUY", "SELL") and self.strategy.side is None:
            qty = self.strategy.calc_qty(
                self.balance,
                df["Close"].iloc[-1],
                decision["sl"],
            )
            qty = math.floor(qty * 1e6) / 1e6
            if qty < 0.0001:
                logger.warning("Qty too small, skip")
                return

            side = "BUY" if decision["action"] == "BUY" else "SELL"
            resp = await self.broker.place_market(self.symbol, side, qty)
            fill_price = resp.get("price")
            if fill_price is None:
                fills = resp.get("fills")
                if fills and isinstance(fills, list) and len(fills) > 0:
                    fill_price = float(fills[0].get("price", 0.0))
                else:
                    fill_price = 0.0
            if not fill_price:
                fill_price = df["Close"].iloc[-1]

            self.strategy.open_position(
                "LONG" if side == "BUY" else "SHORT",
                qty,
                fill_price,
                decision["sl"],
                decision["tp"],
                ts,
            )
            await self.tg.notify(
                f"🏁 *OPEN* {side} {qty:.4f}\nPrice: {fill_price:.2f}"
                f"\nSL: {decision['sl']:.2f}  TP: {decision['tp']:.2f}"
            )
            return

        # ---------- EXIT ---------- #
        if decision["action"] == "EXIT" and self.strategy.side:
            close_side = "SELL" if self.strategy.side == "LONG" else "BUY"
            resp = await self.broker.place_market(
                self.symbol,
                close_side,
                self.strategy.qty,
            )
            exit_price = resp.get("price")
            if exit_price is None:
                fills = resp.get("fills")
                if fills and isinstance(fills, list) and len(fills) > 0:
                    exit_price = float(fills[0].get("price", 0.0))
                else:
                    exit_price = 0.0
            if not exit_price:
                exit_price = df["Close"].iloc[-1]
            closed_trade = self.strategy.close_position(
                exit_price,
                ts,
                reason="SL/TP or signal",
            )

            # Обновляем баланс бота!
            if closed_trade is not None:
                self.balance += closed_trade.pnl
                logger.info(
                    f"Balance updated: {self.balance:.2f} (PnL: {closed_trade.pnl:.2f})"
                )

            await self.tg.notify("✅ *CLOSE* PNL posted")
            return

    # ------------------------------------------------ #
    async def run(self):
        init_db()
        await self.tg.start()
        try:
            await self.feed.start(self.on_candle)
        finally:
            await self.tg.stop()

    async def run_once(self):
        """Fetch one batch of candles and process it once."""
        init_db()
        await self.tg.start()
        try:
            df = await self.feed.fetch_history()
            await self.on_candle(df)
        finally:
            await self.tg.stop()


__all__ = ["LiveTrader"]
