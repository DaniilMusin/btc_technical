import asyncio
import os
from trader import LiveTrader

if __name__ == "__main__":
    asyncio.run(
        LiveTrader(
            os.getenv("DEFAULT_SYMBOL", "BTCUSDT"),
            os.getenv("DEFAULT_INTERVAL", "15m"),
            exchange=os.getenv("EXCHANGE", "BINGX"),
        ).run()
    )
