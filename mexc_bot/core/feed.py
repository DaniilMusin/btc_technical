import datetime as dt
import os
import json
import pandas as pd
from loguru import logger
import asyncio
import websockets
from dotenv import load_dotenv

load_dotenv()
ARCHIVE_CSV = os.getenv("ARCHIVE_CSV", "false").lower() == "true"
ARCHIVE_PATH = "data/ohlc_archive.csv"


class StreamingDataFeed:
    """Subscribe to closed candles and maintain a rolling DataFrame."""

    def __init__(
        self, symbol: str, interval: str, exchange: str = "bingx", max_rows: int = 4000
    ):
        self.symbol, self.interval = symbol.upper(), interval
        self.max_rows = max_rows
        self.exchange = exchange.lower()
        if self.exchange == "mexc":
            try:
                import mexc_sdk  # noqa: F401
            except Exception as e:  # pragma: no cover - just fallback
                logger.warning(f"mexc_sdk import failed: {e}. Falling back to BingX")
                self.exchange = "bingx"
        self.df = pd.DataFrame()

    async def start(self, on_candle):
        if self.exchange == "mexc":
            logger.warning(
                "MEXC streaming not implemented yet, using BingX feed instead"
            )
            self.exchange = "bingx"

        topic = f"kline_{self.interval}_{self.symbol.lower()}"
        url = "wss://open-api.bingx.com/market"

        while True:
            try:
                async with websockets.connect(url) as ws:
                    logger.info(f"Connected to BingX WebSocket for {self.symbol}")
                    payload = {
                        "event": "subscribe",
                        "topic": topic,
                        "params": {"binary": "false"},
                    }
                    await ws.send(json.dumps(payload))
                    async for raw in ws:
                        msg = json.loads(raw)
                        k = msg.get("data") or msg
                        if not k:
                            continue
                        if "c" not in k:  # BingX kline payload
                            continue

                        candle = {
                            "Open time": dt.datetime.fromtimestamp(k["t"] / 1000),
                            "Open": float(k["o"]),
                            "High": float(k["h"]),
                            "Low": float(k["l"]),
                            "Close": float(k["c"]),
                            "Volume": float(k["v"]),
                        }
                        self.df = (
                            pd.concat([self.df, pd.DataFrame([candle])])
                            .tail(self.max_rows)
                            .set_index("Open time")
                        )

                        logger.debug(
                            "Candle %s  O:%.2f C:%.2f V:%.1f",
                            candle["Open time"].strftime("%Y-%m-%d %H:%M"),
                            candle["Open"],
                            candle["Close"],
                            candle["Volume"],
                        )

                        if ARCHIVE_CSV:
                            pd.DataFrame([candle]).to_csv(
                                ARCHIVE_PATH,
                                index=False,
                                mode="a",
                                header=not os.path.exists(ARCHIVE_PATH),
                            )

                        await on_candle(self.df.copy())

            except (
                websockets.ConnectionClosedError,
                websockets.ConnectionClosedOK,
            ) as e:
                logger.error(
                    f"BingX WebSocket connection closed: {e}. Reconnecting in 5 seconds..."
                )
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(
                    f"An unexpected error in feed: {e}. Reconnecting in 10 seconds..."
                )
                await asyncio.sleep(10)
