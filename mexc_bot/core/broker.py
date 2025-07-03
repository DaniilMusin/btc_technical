import hmac
import hashlib
import time
import os
import asyncio
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class BaseBroker:
    """Abstract broker with basic helpers and dry-run support."""

    COMMISSION_RATE_ENTRY = 0.00035
    COMMISSION_RATE_EXIT = 0.00035

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self._client = httpx.AsyncClient(timeout=10.0)
        if testnet:
            logger.warning(
                "%s Broker in DRY-RUN / TESTNET mode – сделки НЕ отправляются",
                self.__class__.__name__,
            )

    # ---- API ---- #
    async def place_market(self, symbol: str, side: str, qty: float):
        raise NotImplementedError

    async def get_balance(self, *args, **kwargs):
        raise NotImplementedError

    async def get_position(self, *args, **kwargs):
        raise NotImplementedError

    async def cancel_all(self, *args, **kwargs):
        raise NotImplementedError

    def log_test(self, symbol: str, side: str, qty: float):
        logger.info("[TESTNET] %s MARKET %s %.6f", symbol, side, qty)


class MexcBroker(BaseBroker):
    """
    Минимальный REST‑клиент для спотовых ордеров MARKET.
    Если USE_TESTNET=true – метод place_market просто пишет в лог вместо отправки.
    """

    def __init__(self, testnet: bool = True):
        super().__init__(testnet)
        self.key = os.getenv("MEXC_API_KEY")
        self.secret = os.getenv("MEXC_API_SECRET", "").encode()
        self.base = "https://api.mexc.com"

    # ---------- helpers ---------- #
    def _sign(self, params: dict) -> dict:
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(self.secret, qs.encode(), hashlib.sha256).hexdigest()
        return params | {"signature": signature}

    async def _post(self, path: str, params: dict):
        p = params | {"timestamp": int(time.time()*1000)}
        while True:
            r = await self._client.post(
                self.base + path,
                params=self._sign(p),
                headers={"X-MEXC-APIKEY": self.key}
            )
            try:
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    await asyncio.sleep(0.25)
                    continue
                raise

    # ---------- public ---------- #
    async def place_market(self, symbol: str, side: str, qty: float) -> dict:
        """
        side = BUY (long)  / SELL (short)
        Возвращает JSON‑ответ биржи или fake‑ответ в тестовом режиме.
        """
        if self.testnet:
            # В тестовом режиме используем «нулевой» resp, но ставим fictive‑price
            logger.info("[TESTNET] %s MARKET %s %.6f", symbol, side, qty)
            return {"fills": [{"price": 0.0}]}

        logger.info("SEND %s MARKET %s %.6f", symbol, side, qty)
        return await self._post("/api/v3/order", {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": qty
        })


class BingxBroker(BaseBroker):
    API_HOST = "https://open-api.bingx.com"
    VERSION = "v3"  # spot version
    KEEP = [
        "symbol",
        "side",
        "type",
        "quantity",
        "price",
        "takeProfit",
        "stopLoss",
    ]

    def __init__(self, testnet: bool = True, symbol: str | None = None):
        super().__init__(testnet)
        self.symbol = (symbol or os.getenv("DEFAULT_SYMBOL", "BTCUSDT")).upper()
        self.qty_precision = 3
        self.price_precision = 1
        self._load_precision()

    def _load_precision(self) -> None:
        """Fetch symbol precision once from BingX."""
        try:
            r = httpx.get(f"{self.API_HOST}/openApi/swap/v2/quote/contracts", timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
            for item in data:
                sym = item.get("symbol", "").replace("-", "").upper()
                if sym == self.symbol.replace("-", ""):
                    self.qty_precision = int(item.get("quantityPrecision", self.qty_precision))
                    self.price_precision = int(item.get("pricePrecision", self.price_precision))
                    break
        except Exception as exc:
            logger.warning("Failed to load precision: %s", exc)

    def _round_qty(self, qty: float) -> float:
        return round(qty, self.qty_precision)

    def _round_price(self, price: float) -> float:
        return round(price, self.price_precision)

    def _sign(self, params: dict) -> dict:
        params |= {"timestamp": int(time.time() * 1000)}
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sig = hmac.new(
            os.getenv("BINGX_API_SECRET", "").encode(), qs.encode(), hashlib.sha256
        ).hexdigest()
        return params | {"signature": sig}

    async def _post(self, path: str, params: dict):
        async with httpx.AsyncClient(timeout=10) as cli:
            while True:
                r = await cli.post(
                    f"{self.API_HOST}{path}",
                    headers={"X-BX-APIKEY": os.getenv("BINGX_API_KEY")},
                    params=self._sign(params),
                )
                try:
                    r.raise_for_status()
                    return r.json()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        await asyncio.sleep(0.25)
                        continue
                    raise

    async def place_market(self, symbol: str, side: str, qty: float):
        qty = self._round_qty(qty)
        if self.testnet:
            self.log_test(symbol, side, qty)
            return {"price": 0.0}
        return await self._post(
            "/openApi/swap/v2/trade/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
                "marginMode": "isolated",
                "leverage": 3,
            },
        )
