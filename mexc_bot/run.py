import asyncio
import os
from core.trader import LiveTrader

if __name__ == "__main__":
    asyncio.run(
        LiveTrader(
            os.getenv("DEFAULT_SYMBOL","BTCUSDT"),
            os.getenv("DEFAULT_INTERVAL","15m")
        ).run()
    )
