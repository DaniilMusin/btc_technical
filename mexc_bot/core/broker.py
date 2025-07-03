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
        self.margin_mode = os.getenv("BINGX_MARGIN_MODE", "isolated")
        self.leverage = int(os.getenv("BINGX_LEVERAGE", 3))
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

    def _prepare_params(self, params: dict) -> dict:
        data = {k: v for k, v in params.items() if k in self.KEEP}
        if "quantity" in data:
            data["quantity"] = self._round_qty(float(data["quantity"]))
        for key in ("price", "takeProfit", "stopLoss"):
            if key in data:
                data[key] = self._round_price(float(data[key]))
        return data

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

    async def place_market(
        self,
        symbol: str,
        side: str,
        qty: float,
        take_profit: float | None = None,
        stop_loss: float | None = None,
    ):
        params = self._prepare_params(
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
                "takeProfit": take_profit,
                "stopLoss": stop_loss,
            }
        )
        params |= {"marginMode": "isolated", "leverage": 3}
        if self.testnet:
            self.log_test(symbol, side, params["quantity"])
            return {"price": 0.0}
        return await self._post("/openApi/swap/v2/trade/order", params)

    async def place_limit(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        take_profit: float | None = None,
        stop_loss: float | None = None,
    ):
        params = self._prepare_params(
            {
                "symbol": symbol,
                "side": side,
                "type": "LIMIT",
                "quantity": qty,

                "price": price,
                "takeProfit": take_profit,
                "stopLoss": stop_loss,
            }
        )
        
        params |= {"marginMode": self.margin_mode, "leverage": self.leverage}
        if self.testnet:
            logger.info(
                "[TESTNET] %s LIMIT %s %.6f @ %.2f",
                symbol,
                side,
                params["quantity"],
                params["price"],
            )
            return {"price": params["price"]}
        return await self._post("/openApi/swap/v2/trade/order", params)
