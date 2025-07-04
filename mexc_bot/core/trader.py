"""Trading helpers used by the CLI entrypoints and tests."""

from __future__ import annotations

import asyncio
import math
import os
from dotenv import load_dotenv
from loguru import logger

from .feed import StreamingDataFeed
from .broker import BingxBroker
from .strategy import BalancedAdaptiveStrategyLive
from .db import init_db
from services.telegram_bot import TgNotifier

load_dotenv()


class LiveTrader:
    """Simple wrapper that glues together feed, broker and strategy."""

    def __init__(self, symbol: str, interval: str, exchange: str = "BINGX"):
        self.symbol, self.interval = symbol.upper(), interval
        self.exchange = exchange.upper()
        self.testnet = os.getenv("USE_TESTNET", "true").lower() == "true"

        # modules
        self.feed = StreamingDataFeed(self.symbol, self.interval)
        if self.exchange != "BINGX":
            raise NotImplementedError(f"Exchange {self.exchange} is not supported")
        self.broker = BingxBroker(testnet=self.testnet, symbol=self.symbol)
        self.strategy = BalancedAdaptiveStrategyLive(
            initial_balance=float(os.getenv("INITIAL_BALANCE", 1000))
        )
        self.tg = TgNotifier()
        self.balance = float(os.getenv("INITIAL_BALANCE", 1000))

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

