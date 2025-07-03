import datetime as dt
import os
import pandas as pd
from loguru import logger
from mexc_sdk import WsSpot  # spot. Для фьючей: WsContract
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
        self.ws = WsSpot()

    async def start(self, on_candle):
        topic = f"spot@public.kline.v3.api@{self.symbol}@{self.interval}"
        async for msg in self.ws.subscribe(topic):
            # ---------- валидация сообщения ---------- #
            if not msg or "d" not in msg:
                continue
            k = msg["d"]
            if k["e"] != "kline" or k.get("x") is False:
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
                candle["Open"], candle["Close"], candle["Volume"]
            )

            # ---------- (опц.) архивируем ---------- #
            if ARCHIVE_CSV:
                # append – быстрее, чем перезаписывать
                pd.DataFrame([candle]).to_csv(
                    ARCHIVE_PATH, index=False, mode="a",
                    header=not os.path.exists(ARCHIVE_PATH)
                )

            await on_candle(self.df.copy())
