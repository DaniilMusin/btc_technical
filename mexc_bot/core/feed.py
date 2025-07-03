import datetime as dt
import os
import json
import pandas as pd
from loguru import logger
from mexc_sdk import WsSpot  # spot. Для фьючей: WsContract
import websockets
import asyncio
from dotenv import load_dotenv

load_dotenv()
ARCHIVE_CSV = os.getenv("ARCHIVE_CSV", "false").lower() == "true"
ARCHIVE_PATH = "data/ohlc_archive.csv"


class StreamingDataFeed:
    """
    Подписывается на закрытые свечи («x»: true) и сохраняет rolling‑DataFrame.
    При ARCHIVE_CSV=true каждую свечу добавляет в CSV‑архив.
    """

    def __init__(self, symbol: str, interval: str, max_rows: int = 4000):
        self.symbol, self.interval = symbol.upper(), interval
        self.max_rows = max_rows
        self.df = pd.DataFrame()
        self.exchange = os.getenv("EXCHANGE", "MEXC").upper()
        if self.exchange == "MEXC":
            self.ws = WsSpot()
        else:
            self.ws = None

    async def start(self, on_candle):
        if self.exchange == "MEXC":
            topic = f"spot@public.kline.v3.api@{self.symbol}@{self.interval}"
            async for msg in self.ws.subscribe(topic):
                if not msg or "d" not in msg:
                    continue
                k = msg["d"]
                if k.get("e") != "kline" or k.get("x") is False:
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
                    candle["Open"], candle["Close"], candle["Volume"],
                )

                if ARCHIVE_CSV:
                    pd.DataFrame([candle]).to_csv(
                        ARCHIVE_PATH,
                        index=False,
                        mode="a",
                        header=not os.path.exists(ARCHIVE_PATH),
                    )

                await on_candle(self.df.copy())
        else:
            topic = f"kline_{self.interval}_{self.symbol.lower()}"
            payload = {"event": "subscribe", "topic": topic, "params": {"binary": "false"}}
            while True:
                try:
                    async with websockets.connect("wss://open-api.bingx.com/market") as ws:
                        await ws.send(json.dumps(payload))
                        async for raw in ws:
                            msg = json.loads(raw)
                            k = msg.get("data") or msg
                            if not k:
                                continue
                            if "c" not in k:
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
                                candle["Open"], candle["Close"], candle["Volume"],
                            )

                            if ARCHIVE_CSV:
                                pd.DataFrame([candle]).to_csv(
                                    ARCHIVE_PATH,
                                    index=False,
                                    mode="a",
                                    header=not os.path.exists(ARCHIVE_PATH),
                                )

                            await on_candle(self.df.copy())
                except websockets.exceptions.ConnectionClosed as e:
                    logger.info("Websocket closed: %s", e)
                except Exception as e:
                    logger.error("Websocket error: %s", e)
                logger.info("Reconnecting in 5s...")
                await asyncio.sleep(5)
