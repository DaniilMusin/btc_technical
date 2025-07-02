import asyncio, os, math
from dotenv import load_dotenv
from loguru import logger

from core.feed import StreamingDataFeed
from core.broker import MexcBroker
from core.strategy import BalancedAdaptiveStrategyLive
from core.db import init_db
from services.telegram_bot import TgNotifier

load_dotenv()

class LiveTrader:
    def __init__(self, symbol: str, interval: str):
        self.symbol, self.interval = symbol.upper(), interval
        self.testnet  = os.getenv("USE_TESTNET","true").lower()=="true"

        # modules
        self.feed     = StreamingDataFeed(self.symbol, self.interval)
        self.broker   = MexcBroker(testnet=self.testnet)
        self.strategy = BalancedAdaptiveStrategyLive(
            initial_balance=float(os.getenv("INITIAL_BALANCE",1000))
        )
        self.tg       = TgNotifier()
        self.balance  = float(os.getenv("INITIAL_BALANCE",1000))

    # ------------------------------------------------ #
    async def on_candle(self, df):
        ts = df.index[-1]           # время закрытия текущей свечи
        decision = self.strategy.on_new_candle(df)

        # ---------- OPEN ---------- #
        if decision["action"] in ("BUY","SELL") and self.strategy.side is None:
            qty = self.strategy.calc_qty(self.balance, df['Close'].iloc[-1], decision["sl"])
            qty = math.floor(qty*1e6)/1e6
            if qty < 0.0001:
                logger.warning("Qty too small, skip")
                return

            side = "BUY" if decision["action"]=="BUY" else "SELL"
            resp = await self.broker.place_market(self.symbol, side, qty)
            fill_price = float(resp["fills"][0]["price"]) or df['Close'].iloc[-1]

            self.strategy.open_position(
                "LONG" if side=="BUY" else "SHORT",
                qty, fill_price, decision["sl"], decision["tp"], ts
            )
            await self.tg.notify(
                f"🏁 *OPEN* {side} {qty:.4f}\nPrice: {fill_price:.2f}"
                f"\nSL: {decision['sl']:.2f}  TP: {decision['tp']:.2f}"
            )
            return

        # ---------- EXIT ---------- #
        if decision["action"]=="EXIT" and self.strategy.side:
            close_side = "SELL" if self.strategy.side=="LONG" else "BUY"
            resp = await self.broker.place_market(
                self.symbol, close_side, self.strategy.qty
            )
            exit_price = float(resp["fills"][0]["price"]) or df['Close'].iloc[-1]
            self.strategy.close_position(exit_price, ts, reason="SL/TP or signal")
            await self.tg.notify(f"✅ *CLOSE* PNL posted")
            return

    # ------------------------------------------------ #
    async def run(self):
        init_db()
        await self.tg.start()
        try:
            await self.feed.start(self.on_candle)
        finally:
            await self.tg.stop()
            await self.broker.close()

# ---------------- script entry ----------------#
if __name__ == "__main__":
    sym = os.getenv("DEFAULT_SYMBOL","BTCUSDT")
    interval = os.getenv("DEFAULT_INTERVAL","15m")
    asyncio.run(LiveTrader(sym, interval).run())
