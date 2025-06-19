import datetime as dt
import os
import pandas as pd
from loguru import logger
import json
import websockets
from dotenv import load_dotenv

load_dotenv()
ARCHIVE_CSV = os.getenv("ARCHIVE_CSV","false").lower() == "true"
ARCHIVE_PATH = "data/ohlc_archive.csv"
HISTORY_MONTHS = int(os.getenv("HISTORY_MONTHS", "3"))

class StreamingDataFeed:
    """
    Подписывается на закрытые свечи («x»: true) и сохраняет rolling‑DataFrame.
    При ARCHIVE_CSV=true каждую свечу добавляет в CSV‑архив.
    """

    def __init__(self, symbol: str, interval: str, max_rows: int | None = None):
        self.symbol, self.interval = symbol.upper(), interval
        self.max_rows = max_rows or self._rows_for_interval(interval)
        self.df = pd.DataFrame()
        self.ws_url = "wss://wbs.mexc.com/ws"

    def _rows_for_interval(self, interval: str) -> int:
        """Return number of rows roughly equal to HISTORY_MONTHS of data."""
        unit = interval[-1]
        try:
            value = int(interval[:-1])
        except ValueError:
            return 4000
        minutes = value if unit == "m" else value * 60 if unit == "h" else value * 60 * 24
        days = HISTORY_MONTHS * 30
        return max(int(days * 24 * 60 / minutes), 1)

    async def start(self, on_candle):
        topic = f"spot@public.kline.v3.api@{self.symbol}@{self.interval}"
        async with websockets.connect(self.ws_url) as ws:
            await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": [topic], "id": 1}))
            async for raw in ws:
                msg = json.loads(raw)
                if "ping" in msg:
                    await ws.send(json.dumps({"pong": msg["ping"]}))
                    continue
                # ---------- валидация сообщения ---------- #
                if not msg or "d" not in msg:
                    continue
                k = msg["d"]
                if k.get("e") != "kline" or not k.get("x"):
                    continue

                candle = {
                    "Open time": dt.datetime.fromtimestamp(k["t"]/1000),
                    "Open"     : float(k["o"]),
                    "High"     : float(k["h"]),
                    "Low"      : float(k["l"]),
                    "Close"    : float(k["c"]),
                    "Volume"   : float(k["v"]),
                }
                self.df = (
                    pd.concat([self.df, pd.DataFrame([candle])])
                    .set_index("Open time")
                )
                cutoff = dt.datetime.utcnow() - dt.timedelta(days=HISTORY_MONTHS * 30)
                self.df = self.df[self.df.index >= cutoff].tail(self.max_rows)

                logger.debug(
                    "Candle %s  O:%.2f C:%.2f V:%.1f",
                    candle["Open time"].strftime("%Y-%m-%d %H:%M"),
                    candle["Open"], candle["Close"], candle["Volume"]
                )

                # ---------- (опц.) архивируем ---------- #
                if ARCHIVE_CSV:
                    if os.path.exists(ARCHIVE_PATH):
                        arch = pd.read_csv(ARCHIVE_PATH, parse_dates=["Open time"])
                    else:
                        arch = pd.DataFrame()
                    arch = pd.concat([arch, pd.DataFrame([candle])])
                    cutoff = dt.datetime.utcnow() - dt.timedelta(days=HISTORY_MONTHS * 30)
                    arch = arch[arch["Open time"] >= cutoff]
                    arch.to_csv(ARCHIVE_PATH, index=False)

                await on_candle(self.df.copy())
