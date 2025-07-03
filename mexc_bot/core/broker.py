import hmac
import hashlib
import time
import os
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

class MexcBroker:
    """
    Минимальный REST‑клиент для спотовых ордеров MARKET.
    Если USE_TESTNET=true – метод place_market просто пишет в лог вместо отправки.
    """

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.key = os.getenv("MEXC_API_KEY")
        self.secret = os.getenv("MEXC_API_SECRET", "").encode()
        self.base = "https://api.mexc.com"
        self._client = httpx.AsyncClient(timeout=10.0)

        if testnet:
            logger.warning(
                "MEXC Broker in DRY‑RUN / TESTNET mode – сделки НЕ отправляются"
            )

    # ---------- helpers ---------- #
    def _sign(self, params: dict) -> dict:
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(self.secret, qs.encode(), hashlib.sha256).hexdigest()
        return params | {"signature": signature}

    async def _post(self, path: str, params: dict):
        p = params | {"timestamp": int(time.time()*1000)}
        r = await self._client.post(
            self.base + path,
            params=self._sign(p),
            headers={"X-MEXC-APIKEY": self.key}
        )
        r.raise_for_status()
        return r.json()

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
