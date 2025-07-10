"""
Live‑адаптер для BalancedAdaptiveStrategy.
Добавлены:
  • warm‑up‑фильтр (минимум 300 свечей)
  • трейлинг‑параметры из env‑переменных
  • fix: используем close‑price при тестнет‑ответе 0.0
"""
from __future__ import annotations
import datetime as dt
import os
import pandas as pd
from typing import Optional, Literal, Dict, Any

from loguru import logger
from dotenv import load_dotenv
from .balanced_strategy_base import BalancedAdaptiveStrategy
from .db import store_trade, last_n_pnl

load_dotenv()
WARMUP_CANDLES = int(os.getenv("WARMUP_CANDLES", "300"))
TRAIL_TRIGGER_LONG_PCT = float(os.getenv("TRAIL_TRIGGER_LONG", "0.04"))
TRAIL_TRIGGER_SHORT_PCT = float(os.getenv("TRAIL_TRIGGER_SHORT", "0.04"))
TRAIL_SL_LONG_PCT = float(os.getenv("TRAIL_SL_LONG", "0.02"))  # 2 %
TRAIL_SL_SHORT_PCT = float(os.getenv("TRAIL_SL_SHORT", "0.02"))

class BalancedAdaptiveStrategyLive(BalancedAdaptiveStrategy):
    def __init__(self, **kw):
        # убираем data_path
        super().__init__(data_path=None, **kw)
        self.data = pd.DataFrame()

        # open position
        self.side      : Optional[Literal["LONG","SHORT"]] = None
        self.qty       : float   = 0.0
        self.entry     : float   = 0.0
        self.sl        : float   = 0.0
        self.tp        : float   = 0.0
        self.entry_dt  : Optional[dt.datetime] = None

    # ---------------- helper utils ---------------- #
    def _should_exit(self, cur_price: float) -> bool:
        if self.side == "LONG":
            return cur_price <= self.sl or cur_price >= self.tp
        if self.side == "SHORT":
            return cur_price >= self.sl or cur_price <= self.tp
        return False

    # ---------------- main API ---------------- #
    def on_new_candle(self, df: pd.DataFrame) -> Dict[str, Any]:
        # ---------- warm‑up ---------- #
        if len(df) < WARMUP_CANDLES:
            return {"action": "NONE"}

        self.data = df.tail(450)            # ускоряем расчёт
        self.calculate_indicators()

        cur, prev = self.data.iloc[-1], self.data.iloc[-2]
        regime = "trend" if cur["Trend_Weight"] > 0.5 else "range"

        # ---------- already in position ---------- #
        if self.side:
            if self._should_exit(cur["Close"]):
                return {"action": "EXIT"}

            # simple trailing‑stop
            if self.side == "LONG" and cur["Close"] > self.entry * (1 + TRAIL_TRIGGER_LONG_PCT):
                new_sl = max(self.sl, cur["Close"] * (1 - TRAIL_SL_LONG_PCT))
                if new_sl != self.sl:
                    logger.info("Update trailing SL (LONG) %.2f → %.2f", self.sl, new_sl)
                    self.sl = new_sl
            elif self.side == "SHORT" and cur["Close"] < self.entry * (1 - TRAIL_TRIGGER_SHORT_PCT):
                new_sl = min(self.sl, cur["Close"] * (1 + TRAIL_SL_SHORT_PCT))
                if new_sl != self.sl:
                    logger.info("Update trailing SL (SHORT) %.2f → %.2f", self.sl, new_sl)
                    self.sl = new_sl
            return {"action": "NONE"}

        # ---------- ищем вход ---------- #
        signals = self.get_trading_signals(cur, prev, regime)
        filt    = self.apply_advanced_filtering(cur, signals)

        long_ok  = filt["long_weight"]  >= 0.65 and filt["long_weight"]  > filt["short_weight"]
        short_ok = filt["short_weight"] >= 0.65 and filt["short_weight"] > filt["long_weight"]

        if long_ok:
            lvls = self.calculate_dynamic_exit_levels("LONG", cur["Close"], cur)
            return {"action": "BUY", "sl": lvls["stop_loss"], "tp": lvls["take_profit"]}

        if short_ok:
            lvls = self.calculate_dynamic_exit_levels("SHORT", cur["Close"], cur)
            return {"action": "SELL", "sl": lvls["stop_loss"], "tp": lvls["take_profit"]}

        return {"action": "NONE"}

    # ---------------- position setters ---------------- #
    def open_position(self, side: Literal["LONG","SHORT"], qty: float,
                      entry_price: float, sl: float, tp: float, ts: dt.datetime):
        self.side, self.qty, self.entry = side, qty, entry_price
        self.sl, self.tp, self.entry_dt = sl, tp, ts
        logger.success("POS OPEN %s qty=%.4f EP=%.2f SL=%.2f TP=%.2f",
                       side, qty, entry_price, sl, tp)

    def close_position(self, exit_price: float, ts: dt.datetime, reason: str):
        if not self.side:
            return None  # Возвращаем None, если позиции нет
        pnl = (
            (exit_price - self.entry) * self.qty
            if self.side == "LONG"
            else (self.entry - exit_price) * self.qty
        )

        trade = store_trade(
            entry_date = self.entry_dt,
            exit_date  = ts,
            position   = self.side,
            qty        = self.qty,
            entry_price= self.entry,
            exit_price = exit_price,
            pnl        = pnl,
            reason     = reason
        )
        logger.success("POS CLOSE %s pnl=%.2f  reason=%s", self.side, pnl, reason)
        self.side = None                         # reset state
        return trade

    # ---------------- динамический размер ---------------- #
    def calc_qty(self, balance: float, price: float, sl: float) -> float:
        """
        Полностью использует adaptive_position_sizing вашего класса:
        рассчитываем %‑риск (по статистике) и размер позы в *BASE‑валюте* (например, BTC).
        """
        risk_pct = self.base_risk_per_trade
        pnl_list = last_n_pnl(20)
        if pnl_list:
            wr = sum(p>0 for p in pnl_list) / len(pnl_list)
            risk_pct *= 0.8 if wr < 0.4 else (1.2 if wr > 0.6 else 1.0)

        risk_usd = balance * risk_pct
        if price and price != sl and price > 0:
            price_risk_pct = abs(price - sl) / price
        else:
            price_risk_pct = 0.001
        
        # Дополнительная проверка на корректность значений
        if price <= 0 or price_risk_pct <= 0:
            logger.warning(f"Invalid values: price={price}, price_risk_pct={price_risk_pct}")
            return 0.0001
            
        qty = risk_usd / (price * price_risk_pct)
        return max(qty, 0.0001)         # минимальный лот BTC

