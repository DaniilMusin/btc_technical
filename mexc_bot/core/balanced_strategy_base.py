import pandas as pd 
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)  # (3) Точечная фильтрация
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Магические числа
COMMISSION_RATE = 0.0008  # 0.08% round-trip
SLIPPAGE_PCT = 0.05       # 0.05% по умолчанию
MIN_BALANCE = 1000
MIN_POSITION = 100

logging.basicConfig(level=logging.INFO)

@dataclass
class StrategyConfig:
    """Configuration class for strategy parameters"""
    short_ema: int = 8
    long_ema: int = 25
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    adx_period: int = 14
    adx_strong_trend: int = 20  # was 25, now 20
    adx_weak_trend: int = 15    # was 20, now 15
    bb_period: int = 20
    bb_std: int = 2
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    atr_multiplier_sl: float = 2.5
    atr_multiplier_tp: float = 7.0
    pyramid_size_multiplier: float = 0.7
    max_pyramid_entries: int = 3
    pyramid_min_profit: float = 0.03
    volume_ma_period: int = 20
    volume_threshold: float = 1.4
    trend_lookback: int = 20
    trend_threshold: float = 0.1
    trading_hours_start: int = 8
    trading_hours_end: int = 16
    adx_min: int = 15
    adx_max: int = 35
    regime_volatility_lookback: int = 100
    regime_direction_short: int = 20
    regime_direction_medium: int = 50
    regime_direction_long: int = 100
    mean_reversion_lookback: int = 20
    mean_reversion_threshold: float = 2.0
    hourly_ema_fast: int = 9
    hourly_ema_slow: int = 30
    four_hour_ema_fast: int = 9
    four_hour_ema_slow: int = 30
    health_trend_weight: float = 0.3
    health_volatility_weight: float = 0.2
    health_volume_weight: float = 0.2
    health_breadth_weight: float = 0.2
    health_sr_weight: float = 0.1
    momentum_roc_periods: tuple = (5, 10, 20, 50)
    momentum_reversal_threshold: int = 5
    optimal_trading_hours: Optional[list] = None
    optimal_trading_days: Optional[list] = None
    long_entry_threshold: float = 0.65
    short_entry_threshold: float = 0.7
    min_trades_interval: int = 12
    global_long_boost: float = 1.10
    global_short_penalty: float = 0.90
    adx_min_for_long: int = 22

class BalancedAdaptiveStrategy:
    def __init__(self, data_path: str, 
                 initial_balance: float = 1000, max_leverage: int = 3, 
                 base_risk_per_trade: float = 0.02, 
                 min_trades_interval: int = 12):
        """Initialization of balanced adaptive strategy for BTC futures trading"""
        self.data_path = data_path
        self.initial_balance = initial_balance
        self.max_leverage = max_leverage
        self.base_risk_per_trade = base_risk_per_trade
        self.min_trades_interval = min_trades_interval
        self.slippage_pct = SLIPPAGE_PCT
        self.params = {
            'short_ema': 8,
            'long_ema': 25,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'adx_period': 14,
            'adx_strong_trend': 20,  # was 25, now 20
            'adx_weak_trend': 15,    # was 20, now 15
            'bb_period': 20,
            'bb_std': 2,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'atr_period': 14,
            'atr_multiplier_sl': 2.5,
            'atr_multiplier_tp': 7.0,
            'pyramid_size_multiplier': 0.7,
            'max_pyramid_entries': 3,
            'pyramid_min_profit': 0.03,
            'volume_ma_period': 20,
            'volume_threshold': 1.4,
            'trend_lookback': 20,
            'trend_threshold': 0.1,
            'trading_hours_start': 8,
            'trading_hours_end': 16,
            'adx_min': 15,
            'adx_max': 35,
            'regime_volatility_lookback': 100,
            'regime_direction_short': 20,
            'regime_direction_medium': 50,
            'regime_direction_long': 100,
            'mean_reversion_lookback': 20,
            'mean_reversion_threshold': 2.0,
            'hourly_ema_fast': 9,
            'hourly_ema_slow': 30,
            'four_hour_ema_fast': 9,
            'four_hour_ema_slow': 30,
            'health_trend_weight': 0.3,
            'health_volatility_weight': 0.2,
            'health_volume_weight': 0.2,
            'health_breadth_weight': 0.2,
            'health_sr_weight': 0.1,
            'momentum_roc_periods': (5, 10, 20, 50),
            'momentum_reversal_threshold': 5,
            'optimal_trading_hours': None,
            'optimal_trading_days': None,
            'long_entry_threshold': 0.65,
            'short_entry_threshold': 0.7,
            'min_trades_interval': 12,
            'global_long_boost': 1.10,
            'global_short_penalty': 0.90,
            'adx_min_for_long': 22,
        }
        self.data = pd.DataFrame()  # <-- live-режим: пустой DataFrame
        self.trade_history = []
        self.backtest_results = None
        self.trade_df: Optional[pd.DataFrame] = None
        self.optimized_params: Optional[Dict[str, Any]] = None
        self.max_price_seen = 0
        self.min_price_seen = float('inf')
        self.current_side = None
    
    def load_data(self) -> Optional[pd.DataFrame]:
        """
        Загружает данные из CSV, приводит индексы и имена колонок к нужному виду.
        """
        import warnings
        if not self.data_path:
            warnings.warn("data_path не задан, load_data() ничего не делает", RuntimeWarning)
            return self.data
        df = pd.read_csv(self.data_path)
        # Попытка найти колонку с датой
        date_col = None
        for col in ['Date', 'date', 'Open time', 'open_time', 'timestamp']:
            if col in df.columns:
                date_col = col
                break
        if date_col is None:
            raise ValueError("Не найдена колонка с датой/временем в файле данных")
        df[date_col] = pd.to_datetime(df[date_col])
        df.set_index(date_col, inplace=True)
        # Приводим имена колонок к Title Case (Open, High, Low, Close, Volume)
        rename_map = {c: c.title() for c in df.columns}
        df.rename(columns=rename_map, inplace=True)
        self.data = df
        return self.data
    
    def validate_data(self) -> None:
        """
        Проверяет наличие минимального набора колонок.
        """
        required = {'Open','High','Low','Close','Volume'}
        missing  = required - set(self.data.columns)
        if missing:
            raise ValueError(f"В данных отсутствуют необходимые колонки: {missing}")
        return
    
    def optimize_memory(self) -> None:
        """Optimize memory usage by converting data types"""
        float_cols = self.data.select_dtypes(include=['float64']).columns
        self.data[float_cols] = self.data[float_cols].astype('float32')
        # Конвертируем bool колонки
        bool_cols = [
            'Bullish_Trend', 'Bearish_Trend', 'Active_Hours', 'Choppy_Market',
            'Bullish_Divergence', 'Bearish_Divergence', 'Balanced_Long_Signal',
            'Balanced_Short_Signal', 'MR_Long_Signal', 'MR_Short_Signal',
            'Strong_Trend', 'Weak_Trend', 'Bullish_Engulfing', 'Bearish_Engulfing'
        ]
        for col in bool_cols:
            if col in self.data.columns:
                self.data[col] = self.data[col].astype('bool')
    
    def calculate_indicators(self) -> pd.DataFrame:
        """
        Calculate expanded set of technical indicators.
        Returns:
            pd.DataFrame: DataFrame with calculated indicators
        Raises:
            ValueError: If data is not loaded or invalid
        """
        logging.info("Calculating indicators...")
        
        # --- EMA ---
        short_ema = self.params['short_ema']
        long_ema = self.params['long_ema']
        self.data[f'EMA_{short_ema}'] = self._calculate_ema(self.data['Close'], short_ema)
        self.data[f'EMA_{long_ema}'] = self._calculate_ema(self.data['Close'], long_ema)
        
        # --- RSI ---
        self.data['RSI'] = self._calculate_rsi(self.data['Close'], self.params['rsi_period'])
        
        # --- Bollinger Bands ---
        bb_std = self.params['bb_std']
        bb_period = self.params['bb_period']
        self.data['BB_Middle'] = self.data['Close'].rolling(window=bb_period).mean()
        rolling_std = self.data['Close'].rolling(window=bb_period).std()
        self.data['BB_Upper'] = self.data['BB_Middle'] + (rolling_std * bb_std)
        self.data['BB_Lower'] = self.data['BB_Middle'] - (rolling_std * bb_std)
        
        # --- ATR for dynamic stop-losses ---
        self.data['ATR'] = self._calculate_atr(
            self.data['High'], 
            self.data['Low'], 
            self.data['Close'], 
            self.params['atr_period']
        )
        
        # Add ATR moving average for volatility calculation
        self.data['ATR_MA'] = self.data['ATR'].rolling(20).mean()
        self.data['ATR_MA'].replace(0, 1e-10, inplace=True)  # (4) Стабильная колонка для деления
        
        # --- ADX ---
        adx_period = self.params['adx_period']
        adx_results = self._calculate_adx(
            self.data['High'], 
            self.data['Low'], 
            self.data['Close'], 
            adx_period
        )
        self.data['ADX'] = adx_results['ADX']
        self.data['Plus_DI'] = adx_results['Plus_DI']
        self.data['Minus_DI'] = adx_results['Minus_DI']
        
        # --- MACD ---
        macd_results = self._calculate_macd(
            self.data['Close'], 
            self.params['macd_fast'], 
            self.params['macd_slow'], 
            self.params['macd_signal']
        )
        self.data['MACD'] = macd_results['MACD']
        self.data['MACD_Signal'] = macd_results['MACD_Signal']
        self.data['MACD_Hist'] = macd_results['MACD_Hist']
        
        # --- Volume filter ---
        self.data['Volume_MA'] = self.data['Volume'].rolling(window=self.params['volume_ma_period']).mean()
        self.data['Volume_Ratio'] = self.data['Volume'] / self.data['Volume_MA']
        
        # --- Trend determination by price movement ---
        lookback = self.params['trend_lookback']
        self.data['Price_Change_Pct'] = (self.data['Close'] - self.data['Close'].shift(lookback)) / self.data['Close'].shift(lookback)
        
        # --- RSI divergence calculation ---
        # Look at price and RSI minimums/maximums
        self.data['Price_Min'] = self.data['Close'].rolling(5, center=True).min() == self.data['Close']
        self.data['Price_Max'] = self.data['Close'].rolling(5, center=True).max() == self.data['Close']
        self.data['RSI_Min'] = self.data['RSI'].rolling(5, center=True).min() == self.data['RSI']
        self.data['RSI_Max'] = self.data['RSI'].rolling(5, center=True).max() == self.data['RSI']
        
        # Divergences
        self.data['Bullish_Divergence'] = False
        self.data['Bearish_Divergence'] = False
        
        # Find local minimums and maximums
        price_mins = self.data[self.data['Price_Min']].index
        price_maxs = self.data[self.data['Price_Max']].index
        rsi_mins = self.data[self.data['RSI_Min']].index
        rsi_maxs = self.data[self.data['RSI_Max']].index
        
        for i in range(1, len(price_mins)):
            for j in range(1, len(rsi_mins)):
                delta_sec = (pd.Timestamp(rsi_mins[j]) - pd.Timestamp(price_mins[i])).total_seconds()
                if 0 <= delta_sec / 3600 <= 3:
                    price_change = self.data.loc[price_mins[i], 'Close'] - self.data.loc[price_mins[i-1], 'Close']
                    rsi_change = self.data.loc[rsi_mins[j], 'RSI'] - self.data.loc[rsi_mins[j-1], 'RSI']
                    if price_change < 0 and rsi_change > 0:
                        self.data.loc[max(price_mins[i], rsi_mins[j]), 'Bullish_Divergence'] = True
        
        for i in range(1, len(price_maxs)):
            for j in range(1, len(rsi_maxs)):
                delta_sec = (pd.Timestamp(rsi_maxs[j]) - pd.Timestamp(price_maxs[i])).total_seconds()
                if 0 <= delta_sec / 3600 <= 3:
                    price_change = self.data.loc[price_maxs[i], 'Close'] - self.data.loc[price_maxs[i-1], 'Close']
                    rsi_change = self.data.loc[rsi_maxs[j], 'RSI'] - self.data.loc[rsi_maxs[j-1], 'RSI']
                    if price_change > 0 and rsi_change < 0:
                        self.data.loc[max(price_maxs[i], rsi_maxs[j]), 'Bearish_Divergence'] = True
        
        self.data['Bullish_Divergence'].fillna(False, inplace=True)
        self.data['Bearish_Divergence'].fillna(False, inplace=True)
        
        # --- Improved market regime determination ---
        threshold = self.params['trend_threshold']
        self.data['Strong_Trend'] = (self.data['ADX'] > self.params['adx_strong_trend']) & \
                                    (self.data['Price_Change_Pct'].abs() > threshold)
        self.data['Weak_Trend'] = (self.data['ADX'] < self.params['adx_weak_trend']) & \
                                  (self.data['Price_Change_Pct'].abs() < threshold/2)
        
        self.data['Bullish_Trend'] = self.data['Strong_Trend'] & (self.data['Price_Change_Pct'] > 0) & \
                                     (self.data['Plus_DI'] > self.data['Minus_DI'])
        self.data['Bearish_Trend'] = self.data['Strong_Trend'] & (self.data['Price_Change_Pct'] < 0) & \
                                     (self.data['Plus_DI'] < self.data['Minus_DI'])
        
        # Trend weight
        self.data['Trend_Weight'] = np.minimum(1.0, np.maximum(0, 
                                              (self.data['ADX'] - self.params['adx_min']) / 
                                              (self.params['adx_max'] - self.params['adx_min'])))
        
        self.data['Range_Weight'] = 1.0 - self.data['Trend_Weight']
        
        # Time filter
        self.data['Hour'] = self.data.index.hour
        self.data['Active_Hours'] = (self.data['Hour'] >= self.params['trading_hours_start']) & \
                                    (self.data['Hour'] <= self.params['trading_hours_end'])
        
        # MACD signals
        self.data['MACD_Bullish_Cross'] = (self.data['MACD'] > self.data['MACD_Signal']) & \
                                          (self.data['MACD'].shift(1) <= self.data['MACD_Signal'].shift(1))
        self.data['MACD_Bearish_Cross'] = (self.data['MACD'] < self.data['MACD_Signal']) & \
                                          (self.data['MACD'].shift(1) >= self.data['MACD_Signal'].shift(1))
        
        # Higher-timeframe trend detection
        self.data['Daily_Close'] = self.data['Close'].resample('1D').last().reindex(self.data.index, method='ffill')
        self.data['Daily_EMA50'] = self._calculate_ema(self.data['Daily_Close'], 50).ffill()
        self.data['Daily_EMA200'] = self._calculate_ema(self.data['Daily_Close'], 200).ffill()
        self.data['Higher_TF_Bullish'] = self.data['Daily_EMA50'] > self.data['Daily_EMA200']
        self.data['Higher_TF_Bearish'] = self.data['Daily_EMA50'] < self.data['Daily_EMA200']
        
        # Market structure analysis
        self.data['HH'] = self.data['High'].rolling(10).max() > self.data['High'].rolling(20).max().shift(10)
        self.data['HL'] = self.data['Low'].rolling(10).min() > self.data['Low'].rolling(20).min().shift(10)
        self.data['LH'] = self.data['High'].rolling(10).max() < self.data['High'].rolling(20).max().shift(10)
        self.data['LL'] = self.data['Low'].rolling(10).min() < self.data['Low'].rolling(20).min().shift(10)
        self.data['Bullish_Structure'] = self.data['HH'] & self.data['HL']
        self.data['Bearish_Structure'] = self.data['LH'] & self.data['LL']
        
        # Day of week
        self.data['Day_of_Week'] = self.data.index.dayofweek
        self.data['Day_Name'] = self.data['Day_of_Week'].map({
            0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 
            3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'
        })
        
        # Volume analysis improvements
        self.data['Volume_MA_3'] = self.data['Volume'].rolling(window=3).mean()
        self.data['Volume_MA_10'] = self.data['Volume'].rolling(window=10).mean()
        self.data['Rising_Volume'] = self.data['Volume'] > self.data['Volume_MA_3'] * 1.2
        self.data['Falling_Volume'] = self.data['Volume'] < self.data['Volume_MA_3'] * 0.8
        
        # Price action patterns
        self.data['Bullish_Engulfing'] = (
            (self.data['Open'] < self.data['Close'].shift(1)) & 
            (self.data['Close'] > self.data['Open'].shift(1)) & 
            (self.data['Close'] > self.data['Open']) &
            (self.data['Open'].shift(1) > self.data['Close'].shift(1))
        )
        
        self.data['Bearish_Engulfing'] = (
            (self.data['Open'] > self.data['Close'].shift(1)) & 
            (self.data['Close'] < self.data['Open'].shift(1)) & 
            (self.data['Close'] < self.data['Open']) &
            (self.data['Open'].shift(1) < self.data['Close'].shift(1))
        )
        
        # Volatility ratio
        self.data['Volatility_Ratio'] = self.data['ATR'] / self.data['ATR_MA'].replace(0, 1e-10)
        
        # 1. Enhanced Market Regime Detection
        self.detect_market_regime(lookback=self.params['regime_volatility_lookback'])
        
        # 2. Add Counter-Cyclical Indicators
        self.data['Price_to_200MA_Ratio'] = self.data['Close'] / self.data['Daily_EMA200']
        self.data['Extreme_Overbought'] = self.data['Price_to_200MA_Ratio'] > 1.3
        self.data['Extreme_Oversold'] = self.data['Price_to_200MA_Ratio'] < 0.7
        
        # Add momentum oscillator divergence
        self.data['Momentum'] = self.data['Close'] - self.data['Close'].shift(14)
        self.data['Momentum_SMA'] = self.data['Momentum'].rolling(window=10).mean()
        self.data['Price_Up_Momentum_Down'] = (self.data['Close'] > self.data['Close'].shift()) & \
                                              (self.data['Momentum'] < self.data['Momentum'].shift())
        self.data['Price_Down_Momentum_Up'] = (self.data['Close'] < self.data['Close'].shift()) & \
                                              (self.data['Momentum'] > self.data['Momentum'].shift())
        
        # 5. Multi-Timeframe Confirmation
        self.calculate_multi_timeframe_confirmation()
        
        # 6. Mean-Reversion Signals
        self.calculate_mean_reversion_signals()
        
        # 7. Market Cycle Phase Detection
        self.identify_market_cycle_phase()
        
        # 8. Market Health Score
        self.calculate_market_health()
        
        # 9. Momentum and Reversal Metrics
        self.calculate_momentum_metrics()
        
        # 10. Adaptive Trade Management
        self.adapt_to_market_conditions()
        
        # Remove rows with NaN after calculating indicators
        self.data.dropna(inplace=True)
        logging.info(f"After dropna, {len(self.data)} rows remain for backtest.")
        self.optimize_memory()  # Вызов после dropna и создания всех колонок
        logging.info("Indicators calculated")
        return self.data
    
    def detect_market_regime(self, lookback=100):
        """Enhanced market regime detection with fractal patterns"""
        self.data['Market_Regime'] = 'unknown'
        
        for i in range(lookback, len(self.data)):
            recent = self.data.iloc[i-lookback:i+1]
            
            short_period = self.params['regime_direction_short']
            medium_period = self.params['regime_direction_medium']
            long_period = self.params['regime_direction_long']
            
            if len(recent) >= short_period:
                short_direction = (recent['Close'].iloc[-1] - recent['Close'].iloc[-short_period]) / \
                                   recent['Close'].iloc[-short_period]
            else:
                short_direction = 0
            
            if len(recent) >= medium_period:
                medium_direction = (recent['Close'].iloc[-1] - recent['Close'].iloc[-medium_period]) / \
                                    recent['Close'].iloc[-medium_period]
            else:
                medium_direction = 0
            
            if len(recent) >= long_period:
                long_direction = (recent['Close'].iloc[-1] - recent['Close'].iloc[-long_period]) / \
                                  recent['Close'].iloc[-long_period]
            else:
                long_direction = 0
            
            # Calculate volatility
            if len(recent) >= short_period:
                short_vol = recent['Close'].pct_change().rolling(short_period).std().iloc[-1]
            else:
                short_vol = 0
                
            if len(recent) >= medium_period:
                medium_vol = recent['Close'].pct_change().rolling(medium_period).std().iloc[-1]
            else:
                medium_vol = 0
                
            if len(recent) >= long_period:
                long_vol = recent['Close'].pct_change().rolling(long_period).std().iloc[-1]
            else:
                long_vol = 0
            
            vol_expanding = short_vol > medium_vol > long_vol if (medium_vol > 0 and long_vol > 0) else False
            vol_contracting = short_vol < medium_vol < long_vol if (short_vol > 0 and medium_vol > 0) else False
            
            # Identify regimes
            if short_direction > 0.05 and medium_direction > 0.03 and vol_expanding:
                self.data.at[self.data.index[i], 'Market_Regime'] = "strong_bull"
            elif short_direction < -0.05 and medium_direction < -0.03 and vol_expanding:
                self.data.at[self.data.index[i], 'Market_Regime'] = "strong_bear"
            elif abs(short_direction) < 0.02 and vol_contracting:
                self.data.at[self.data.index[i], 'Market_Regime'] = "choppy_range"
            elif short_direction > 0 and medium_direction < 0:
                self.data.at[self.data.index[i], 'Market_Regime'] = "transition_to_bull"
            elif short_direction < 0 and medium_direction > 0:
                self.data.at[self.data.index[i], 'Market_Regime'] = "transition_to_bear"
            else:
                self.data.at[self.data.index[i], 'Market_Regime'] = "mixed"
        
        self.data['Market_Regime'].fillna('unknown', inplace=True)
        
        # Set position size multipliers based on regime
        self.data['Regime_Long_Multiplier'] = 1.0
        self.data['Regime_Short_Multiplier'] = 1.0
        
        regime_multipliers = {
            "strong_bull": {"LONG": 1.2, "SHORT": 0.6},
            "strong_bear": {"LONG": 0.6, "SHORT": 1.2},
            "choppy_range": {"LONG": 0.8, "SHORT": 0.8},
            "transition_to_bull": {"LONG": 1.0, "SHORT": 0.8},
            "transition_to_bear": {"LONG": 0.8, "SHORT": 1.0},
            "mixed": {"LONG": 0.7, "SHORT": 0.7},
            "unknown": {"LONG": 0.7, "SHORT": 0.7}
        }
        
        for regime, multipliers in regime_multipliers.items():
            mask = self.data['Market_Regime'] == regime
            self.data.loc[mask, 'Regime_Long_Multiplier'] = multipliers["LONG"]
            self.data.loc[mask, 'Regime_Short_Multiplier'] = multipliers["SHORT"]
    
    def calculate_multi_timeframe_confirmation(self):
        """Create signals from multiple timeframes for stronger confirmation"""
        try:
            hourly = self.data['Close'].resample('1H').ohlc()
            hourly_ema_fast = self._calculate_ema(hourly['close'], self.params['hourly_ema_fast'])
            hourly_ema_slow = self._calculate_ema(hourly['close'], self.params['hourly_ema_slow'])
            hourly_signal = hourly_ema_fast > hourly_ema_slow
            four_hour = self.data['Close'].resample('4H').ohlc()
            four_hour_ema_fast = self._calculate_ema(four_hour['close'], self.params['four_hour_ema_fast'])
            four_hour_ema_slow = self._calculate_ema(four_hour['close'], self.params['four_hour_ema_slow'])
            four_hour_signal = four_hour_ema_fast > four_hour_ema_slow
            self.data['Hourly_Bullish'] = self.data.index.floor('H').map(hourly_signal).fillna(False)
            self.data['4H_Bullish'] = self.data.index.floor('4H').map(four_hour_signal).fillna(False)
            self.data['MTF_Bull_Strength'] = (
                (self.data['Hourly_Bullish'].astype(int) + 
                 self.data['4H_Bullish'].astype(int) + 
                 self.data['Higher_TF_Bullish'].astype(int)) / 3
            )
            self.data['MTF_Bear_Strength'] = (
                ((~self.data['Hourly_Bullish']).astype(int) + 
                 (~self.data['4H_Bullish']).astype(int) + 
                 self.data['Higher_TF_Bearish'].astype(int)) / 3
            )
        except Exception as e:
            print(f"Error in multi-timeframe calculation: {e}")
            self.data['MTF_Bull_Strength'] = self.data['Higher_TF_Bullish'].astype(int)
            self.data['MTF_Bear_Strength'] = self.data['Higher_TF_Bearish'].astype(int)
    
    def calculate_mean_reversion_signals(self):
        """Calculate mean reversion indicators for range markets"""
        lookback = self.params['mean_reversion_lookback']
        threshold = self.params['mean_reversion_threshold']
        
        self.data['Close_SMA20'] = self.data['Close'].rolling(window=lookback).mean()
        self.data['Price_Deviation'] = self.data['Close'] - self.data['Close_SMA20']
        self.data['Price_Deviation_Std'] = self.data['Price_Deviation'].rolling(window=lookback).std()
        self.data['Z_Score'] = self.data['Price_Deviation'] / self.data['Price_Deviation_Std'].replace(0, np.nan)
        
        self.data['Stat_Overbought'] = self.data['Z_Score'] > threshold
        self.data['Stat_Oversold'] = self.data['Z_Score'] < -threshold
        
        self.data['MR_Long_Signal'] = (
            (self.data['Z_Score'] < -threshold) & 
            (self.data['Z_Score'].shift(1) >= -threshold)
        )
        self.data['MR_Short_Signal'] = (
            (self.data['Z_Score'] > threshold) & 
            (self.data['Z_Score'].shift(1) <= threshold)
        )
    
    def identify_market_cycle_phase(self):
        """Identify market cycle phase using multiple metrics"""
        self.data['Cycle_Phase'] = 'Unknown'
        
        accumulation_mask = (
            (self.data['RSI'] < 40) & 
            (self.data['Volume_Ratio'] > 1.2) & 
            (self.data['Close'] < self.data['Daily_EMA50']) & 
            (self.data['Close'] > self.data['Close'].shift(10))
        )
        self.data.loc[accumulation_mask, 'Cycle_Phase'] = 'Accumulation'
        
        markup_mask = (
            self.data['Bullish_Trend'] & 
            self.data['Higher_TF_Bullish'] & 
            (self.data['Volume_Ratio'] > 1.0)
        )
        self.data.loc[markup_mask, 'Cycle_Phase'] = 'Markup'
        
        distribution_mask = (
            (self.data['RSI'] > 60) & 
            (self.data['Volume_Ratio'] > 1.2) & 
            (self.data['Close'] > self.data['Daily_EMA50']) & 
            (self.data['Close'] < self.data['Close'].shift(10))
        )
        self.data.loc[distribution_mask, 'Cycle_Phase'] = 'Distribution'
        
        markdown_mask = (
            self.data['Bearish_Trend'] & 
            self.data['Higher_TF_Bearish'] & 
            (self.data['Volume_Ratio'] > 1.0)
        )
        self.data.loc[markdown_mask, 'Cycle_Phase'] = 'Markdown'
        
        self.data['Long_Phase_Weight'] = 1.0
        self.data['Short_Phase_Weight'] = 1.0
        
        self.data.loc[self.data['Cycle_Phase'] == 'Accumulation', 'Long_Phase_Weight'] = 1.3
        self.data.loc[self.data['Cycle_Phase'] == 'Accumulation', 'Short_Phase_Weight'] = 0.7
        
        self.data.loc[self.data['Cycle_Phase'] == 'Markup', 'Long_Phase_Weight'] = 1.5
        self.data.loc[self.data['Cycle_Phase'] == 'Markup', 'Short_Phase_Weight'] = 0.5
        
        self.data.loc[self.data['Cycle_Phase'] == 'Distribution', 'Long_Phase_Weight'] = 0.7
        self.data.loc[self.data['Cycle_Phase'] == 'Distribution', 'Short_Phase_Weight'] = 1.3
        
        self.data.loc[self.data['Cycle_Phase'] == 'Markdown', 'Long_Phase_Weight'] = 0.5
        self.data.loc[self.data['Cycle_Phase'] == 'Markdown', 'Short_Phase_Weight'] = 1.5
    
    def calculate_market_health(self):
        """Calculate overall market health score (0-100)"""
        self.data['Trend_Health'] = (self.data['Close'] > self.data['Daily_EMA50']).astype(int) * 20
        
        vol_ratio = self.data['ATR'] / self.data['ATR'].rolling(100).mean().replace(0, 1e-10)
        self.data['Volatility_Health'] = 20 - (vol_ratio - 1).clip(0, 2) * 10
        
        self.data['Volume_Health'] = self.data['Volume_Ratio'].clip(0, 2) * 10
        
        indicators_bullish = (
            (self.data['RSI'] > 50).astype(int) + 
            (self.data['MACD'] > 0).astype(int) + 
            (self.data[f'EMA_{self.params["short_ema"]}'] > self.data[f'EMA_{self.params["long_ema"]}']).astype(int) +
            (self.data['Bullish_Structure']).astype(int)
        ) / 4 * 20
        self.data['Breadth_Health'] = indicators_bullish
        
        bb_position = (self.data['Close'] - self.data['BB_Lower']) / (self.data['BB_Upper'] - self.data['BB_Lower'])
        bb_position = bb_position.replace([np.inf, -np.inf], np.nan).fillna(0.5)
        self.data['Support_Resistance_Health'] = (0.5 - abs(bb_position - 0.5)) * 2 * 20
        
        self.data['Market_Health'] = (
            self.data['Trend_Health'] * self.params['health_trend_weight'] + 
            self.data['Volatility_Health'] * self.params['health_volatility_weight'] + 
            self.data['Volume_Health'] * self.params['health_volume_weight'] + 
            self.data['Breadth_Health'] * self.params['health_breadth_weight'] + 
            self.data['Support_Resistance_Health'] * self.params['health_sr_weight']
        ).clip(0, 100)
        
        self.data['Health_Long_Bias'] = self.data['Market_Health'] / 100
        self.data['Health_Short_Bias'] = 1 - (self.data['Market_Health'] / 100)
        # --- Enhanced Market Health ---
        trend_strength = (self.data['ADX'] / 50).clip(0, 1)
        momentum_health = ((self.data['RSI'] - 50) / 50).clip(-1, 1)
        volume_health = (self.data['Volume_Ratio'] / 2).clip(0, 1)
        self.data['Enhanced_Market_Health'] = (
            trend_strength * 0.3 +
            (momentum_health + 1) / 2 * 0.3 +
            volume_health * 0.2 +
            self.data['Market_Health'] / 100 * 0.2
        ) * 100
    
    def calculate_momentum_metrics(self):
        """Calculate momentum strength and detect potential reversals"""
        periods = self.params['momentum_roc_periods']
        for period in periods:
            self.data[f'ROC_{period}'] = self.data['Close'].pct_change(period) * 100
        
        momentum_components = [
            (np.sign(self.data[f'ROC_{period}']) * self.data[f'ROC_{period}'].abs() ** 0.5) 
            for period in periods
        ]
        self.data['Momentum_Score'] = sum(momentum_components) / len(periods)
        
        max_val = self.data['Momentum_Score'].abs().max()
        if max_val > 0:
            self.data['Momentum_Score'] = self.data['Momentum_Score'] * (100 / max_val)
        
        self.data['Mom_Acceleration'] = self.data['Momentum_Score'].diff(3)
        reversal_threshold = self.params['momentum_reversal_threshold']
        self.data['Potential_Momentum_Reversal'] = (
            ((self.data['Momentum_Score'] > 80) & (self.data['Mom_Acceleration'] < -reversal_threshold)) |
            ((self.data['Momentum_Score'] < -80) & (self.data['Mom_Acceleration'] > reversal_threshold))
        )
        
        self.data['Momentum_Long_Bias'] = ((self.data['Momentum_Score'] + 100) / 200).clip(0.3, 0.7)
        self.data['Momentum_Short_Bias'] = 1 - self.data['Momentum_Long_Bias']
    
    def adapt_to_market_conditions(self):
        """Apply all market condition metrics to create balanced strategy bias"""
        
        self.data['Final_Long_Bias'] = (
            self.data['Health_Long_Bias'] * 0.3 +
            self.data['Momentum_Long_Bias'] * 0.3 +
            self.data['Long_Phase_Weight'] / 2 * 0.2 +
            self.data['MTF_Bull_Strength'] * 0.2
        )
        
        self.data['Final_Short_Bias'] = (
            self.data['Health_Short_Bias'] * 0.3 +
            self.data['Momentum_Short_Bias'] * 0.3 +
            self.data['Short_Phase_Weight'] / 2 * 0.2 +
            self.data['MTF_Bear_Strength'] * 0.2
        )
        
        signal_threshold = 0.65
        
        self.data['Choppy_Market'] = (
            (self.data['Final_Long_Bias'] < signal_threshold) & 
            (self.data['Final_Short_Bias'] < signal_threshold)
        )
        
        self.data['MR_Signal_Weight'] = 0.5
        self.data.loc[self.data['Choppy_Market'], 'MR_Signal_Weight'] = 1.5
        
        self.data['Balanced_Long_Signal'] = (
            (self.data['Final_Long_Bias'] > signal_threshold) |
            (self.data['Choppy_Market'] & self.data['MR_Long_Signal'])
        )
        
        self.data['Balanced_Short_Signal'] = (
            (self.data['Final_Short_Bias'] > signal_threshold) |
            (self.data['Choppy_Market'] & self.data['MR_Short_Signal'])
        )
        
        self.data['Adaptive_Stop_Multiplier'] = np.where(
            self.data['Choppy_Market'],
            self.params['atr_multiplier_sl'] * 1.2,
            self.params['atr_multiplier_sl'] * 0.9
        )
        
        self.data['Adaptive_TP_Multiplier'] = np.where(
            self.data['Choppy_Market'],
            self.params['atr_multiplier_tp'] * 0.8,
            self.params['atr_multiplier_tp'] * 1.2
        )
    
    def adaptive_risk_per_trade(self, current_market_regime, win_rate_long, win_rate_short):
        base_risk = self.base_risk_per_trade
        long_adjustment = 1.0
        short_adjustment = 1.0
        
        if win_rate_long > 0.6:
            long_adjustment = 1.2
        elif win_rate_long < 0.4:
            long_adjustment = 0.8
            
        if win_rate_short > 0.6:
            short_adjustment = 1.2
        elif win_rate_short < 0.4:
            short_adjustment = 0.8
        
        regime_factors = {
            "strong_bull": {"LONG": 1.1, "SHORT": 0.7},
            "strong_bear": {"LONG": 0.7, "SHORT": 1.1},
            "choppy_range": {"LONG": 0.8, "SHORT": 0.8},
            "transition_to_bull": {"LONG": 0.9, "SHORT": 0.8},
            "transition_to_bear": {"LONG": 0.8, "SHORT": 0.9},
            "mixed": {"LONG": 0.7, "SHORT": 0.7},
            "unknown": {"LONG": 0.7, "SHORT": 0.7}
        }
        
        if current_market_regime not in regime_factors:
            current_market_regime = "mixed"
        
        # --- Dynamic risk management ---
        if hasattr(self, 'trade_df') and self.trade_df is not None and len(self.trade_df) > 20:
            last = self.trade_df.tail(20)
            win_rate = (last['pnl'] > 0).mean()
            profit_factor = last[last['pnl'] > 0]['pnl'].sum() / abs(last[last['pnl'] <= 0]['pnl'].sum()) if (last['pnl'] <= 0).any() else 2
            risk_multiplier = 1.0
            if win_rate > 0.6:
                risk_multiplier = 1.3
            elif profit_factor > 2.0:
                risk_multiplier = 1.2
            base_risk *= risk_multiplier
        
        # --- Regime multipliers ---
        return {
            "LONG": base_risk * long_adjustment * regime_factors[current_market_regime]["LONG"],
            "SHORT": base_risk * short_adjustment * regime_factors[current_market_regime]["SHORT"]
        }
    
    def _calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_rsi(self, series, period):
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss.clip(lower=1e-10)  # (6) Исправление replace на clip
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_atr(self, high, low, close, period):
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        return atr
    
    def _calculate_adx(self, high, low, close, period):
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        plus_dm = pd.Series(plus_dm, index=high.index)
        minus_dm = pd.Series(minus_dm, index=high.index)
        
        smooth_plus_dm = plus_dm.rolling(window=period).mean()
        smooth_minus_dm = minus_dm.rolling(window=period).mean()
        
        plus_di = 100 * (smooth_plus_dm / atr.replace(0, 1e-10))
        minus_di = 100 * (smooth_minus_dm / atr.replace(0, 1e-10))
        
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10))
        adx = dx.rolling(window=period).mean()
        
        return {
            'ADX': adx,
            'Plus_DI': plus_di,
            'Minus_DI': minus_di
        }
    
    def _calculate_macd(self, series, fast_period, slow_period, signal_period):
        fast_ema = series.ewm(span=fast_period, adjust=False).mean()
        slow_ema = series.ewm(span=slow_period, adjust=False).mean()
        
        macd = fast_ema - slow_ema
        macd_signal = macd.ewm(span=signal_period, adjust=False).mean()
        macd_hist = macd - macd_signal
        
        return {
            'MACD': macd,
            'MACD_Signal': macd_signal,
            'MACD_Hist': macd_hist
        }
    def get_trading_signals(self, current, previous, regime_type):
        long_signals = []
        short_signals = []
        
        short_ema = self.params['short_ema']
        long_ema = self.params['long_ema']
        
        # --- Daily trend filter (soft) ---
        # If Daily_EMA50 < Daily_EMA200 and not Higher_TF_Bullish, prohibit only LONG
        if ('Daily_EMA50' in current and 'Daily_EMA200' in current and
            current['Daily_EMA50'] < current['Daily_EMA200'] and not current['Higher_TF_Bullish']):
            prohibit_long = True
        else:
            prohibit_long = False
        # If Daily_EMA50 > Daily_EMA200 and not Higher_TF_Bearish, prohibit only SHORT
        if ('Daily_EMA50' in current and 'Daily_EMA200' in current and
            current['Daily_EMA50'] > current['Daily_EMA200'] and not current['Higher_TF_Bearish']):
            prohibit_short = True
        else:
            prohibit_short = False
        
        volume_multiplier = 1.0
        if current['Volume_Ratio'] > self.params['volume_threshold']:
            volume_multiplier = min(2.0, current['Volume_Ratio'] / self.params['volume_threshold'])
        
        health_factor_long = current['Health_Long_Bias']
        health_factor_short = current['Health_Short_Bias']
        
        momentum_factor_long = current['Momentum_Long_Bias']
        momentum_factor_short = current['Momentum_Short_Bias']
        
        phase_factor_long = current.get('Long_Phase_Weight', 1.0)
        phase_factor_short = current.get('Short_Phase_Weight', 1.0)
        
        regime_multiplier_long = current.get('Regime_Long_Multiplier', 1.0)
        regime_multiplier_short = current.get('Regime_Short_Multiplier', 1.0)
        
        if regime_type == 'trend':
            if current['Trend_Weight'] > 0.45:  # was 0.55, now 0.45 for LONG
                # Long signals
                if ((previous[f"EMA_{short_ema}"] < previous[f"EMA_{long_ema}"]) and 
                    (current[f"EMA_{short_ema}"] >= current[f"EMA_{long_ema}"])):
                    signal_weight = (current['Trend_Weight'] * 1.2 *
                                     health_factor_long * momentum_factor_long *
                                     phase_factor_long * regime_multiplier_long)
                    long_signals.append(('EMA Crossover', signal_weight))
                
                if (current['MACD_Bullish_Cross'] and 
                    current['MACD_Hist'] > 0 and 
                    current['MACD_Hist'] > previous['MACD_Hist']):
                    signal_weight = (current['Trend_Weight'] * 1.3 *
                                     health_factor_long * momentum_factor_long *
                                     phase_factor_long * regime_multiplier_long)
                    long_signals.append(('MACD Bullish Cross', signal_weight))
                
                if (current['Bullish_Trend'] and not previous['Bullish_Trend'] and 
                    current['Plus_DI'] > current['Minus_DI'] * 1.2):
                    signal_weight = (current['Trend_Weight'] * 1.5 *
                                     health_factor_long * momentum_factor_long *
                                     phase_factor_long * regime_multiplier_long)
                    long_signals.append(('Strong Bullish Trend', signal_weight))
                
                if current['Higher_TF_Bullish']:
                    for i in range(len(long_signals)):
                        signal, weight = long_signals[i]
                        long_signals[i] = (signal, weight * 1.3)
                
                # Volume Breakout
                if (current['High'] > previous['High'] * 1.002 and
                    current['Volume_Ratio'] > 1.3 and
                    current['Bullish_Trend']):
                    signal_weight = current['Trend_Weight'] * 1.4 * regime_multiplier_long
                    long_signals.append(('Volume Breakout', signal_weight))
                
                # Daily Golden Cross
                if (current['Higher_TF_Bullish'] and not previous['Higher_TF_Bullish']):
                    long_signals.append(('Daily Golden Cross', 1.5))
                
                if current['Balanced_Long_Signal'] and current['Final_Long_Bias'] > 0.60:
                    signal_weight = current['Final_Long_Bias'] * 1.5 * regime_multiplier_long
                    long_signals.append(('Balanced Long Signal', signal_weight))
                
                # --- Enhanced Volume Breakout ---
                if current['Volume_Ratio'] > 1.3 and current['Close'] > previous['High'] * 1.001:
                    signal_weight = current['Trend_Weight'] * 1.4 * regime_multiplier_long
                    long_signals.append(('Enhanced Volume Breakout', signal_weight))
                # --- Support Level Bounce ---
                if (current['Close'] > current['BB_Lower'] * 1.01 and current['RSI'] > 35 and current['ADX'] > 15):
                    signal_weight = 1.3 * regime_multiplier_long
                    long_signals.append(('Support Level Bounce', signal_weight))
                
                # Short signals (keep threshold at 0.6)
                if ((previous[f"EMA_{short_ema}"] > previous[f"EMA_{long_ema}"]) and 
                    (current[f"EMA_{short_ema}"] <= current[f"EMA_{long_ema}"])):
                    signal_weight = (current['Trend_Weight'] * 1.2 *
                                     health_factor_short * momentum_factor_short *
                                     phase_factor_short * regime_multiplier_short)
                    short_signals.append(('EMA Crossover', signal_weight))
                
                if (current['MACD_Bearish_Cross'] and 
                    current['MACD_Hist'] < 0 and 
                    current['MACD_Hist'] < previous['MACD_Hist']):
                    signal_weight = (current['Trend_Weight'] * 1.3 *
                                     health_factor_short * momentum_factor_short *
                                     phase_factor_short * regime_multiplier_short)
                    short_signals.append(('MACD Bearish Cross', signal_weight))
                
                if (current['Bearish_Trend'] and not previous['Bearish_Trend'] and 
                    current['Minus_DI'] > current['Plus_DI'] * 1.2):
                    signal_weight = (current['Trend_Weight'] * 1.5 *
                                     health_factor_short * momentum_factor_short *
                                     phase_factor_short * regime_multiplier_short)
                    short_signals.append(('Strong Bearish Trend', signal_weight))
                
                if current['Higher_TF_Bearish']:
                    for i in range(len(short_signals)):
                        signal, weight = short_signals[i]
                        short_signals[i] = (signal, weight * 1.3)
                
                if current['Balanced_Short_Signal'] and current['Final_Short_Bias'] > 0.65:
                    signal_weight = current['Final_Short_Bias'] * 1.5 * regime_multiplier_short
                    short_signals.append(('Balanced Short Signal', signal_weight))
                    
                # 52-week High Breakout
                rolling_max = self.data['High'].rolling(1440).max().shift(1)
                if (current['High'] > rolling_max.loc[current.name]) and current['Volume_Ratio'] > 1.5:
                    signal_weight = 1.6 * health_factor_long * regime_multiplier_long
                    long_signals.append(('52-week High Break', signal_weight))
                
                # --- Enhanced long signals ---
                if (current['Volume_Ratio'] > 1.5 and current['Close'] > previous['High'] and current['RSI'] > 45):
                    long_signals.append(('Volume Breakout', 1.3))
                if (current['Close'] > current['BB_Lower'] * 1.01 and current['RSI'] > 40 and current['MACD_Hist'] > previous['MACD_Hist']):
                    long_signals.append(('Support Bounce Enhanced', 1.4))
                if (current['Bullish_Engulfing'] and current['Volume_Ratio'] > 1.2 and current['ADX'] > 20):
                    long_signals.append(('Confirmed Bullish Engulfing', 1.5))
        
        else:
            # RANGING MARKET STRATEGY
            if current['Range_Weight'] > 0.6:
                # Long signals
                if (current['RSI'] < self.params['rsi_oversold'] and 
                    current['Close'] < current['BB_Lower'] * 1.01):
                    signal_weight = (current['Range_Weight'] * 1.3 *
                                     health_factor_long * phase_factor_long *
                                     regime_multiplier_long)
                    long_signals.append(('RSI Oversold + BB Lower', signal_weight))
                
                if current['Bullish_Divergence'] and current['RSI'] < 40:
                    signal_weight = (current['Range_Weight'] * 1.6 *
                                     health_factor_long * phase_factor_long *
                                     regime_multiplier_long)
                    long_signals.append(('Strong Bullish Divergence', signal_weight))
                
                if (current['Close'] > current['Open'] and 
                    previous['Close'] < previous['Open'] and
                    current['Low'] > previous['Low'] * 0.998 and
                    current['Volume'] > previous['Volume'] * 1.2):
                    signal_weight = (current['Range_Weight'] * 1.2 *
                                     health_factor_long * phase_factor_long *
                                     regime_multiplier_long)
                    long_signals.append(('Support Bounce', signal_weight))
                
                if current['MR_Long_Signal'] and current['Z_Score'] < -2.0:
                    signal_weight = (current['Range_Weight'] * 1.4 *
                                     current['MR_Signal_Weight'] * regime_multiplier_long)
                    long_signals.append(('Mean Reversion Long', signal_weight))
                
                # Short signals
                if (current['RSI'] > self.params['rsi_overbought'] and 
                    current['Close'] > current['BB_Upper'] * 0.99):
                    signal_weight = (current['Range_Weight'] * 1.3 *
                                     health_factor_short * phase_factor_short *
                                     regime_multiplier_short)
                    short_signals.append(('RSI Overbought + BB Upper', signal_weight))
                
                if current['Bearish_Divergence'] and current['RSI'] > 60:
                    signal_weight = (current['Range_Weight'] * 1.6 *
                                     health_factor_short * phase_factor_short *
                                     regime_multiplier_short)
                    short_signals.append(('Strong Bearish Divergence', signal_weight))
                
                if (current['Close'] < current['Open'] and 
                    previous['Close'] > previous['Open'] and
                    current['High'] < previous['High'] * 1.002 and
                    current['Volume'] > previous['Volume'] * 1.2):
                    signal_weight = (current['Range_Weight'] * 1.2 *
                                     health_factor_short * phase_factor_short *
                                     regime_multiplier_short)
                    short_signals.append(('Resistance Rejection', signal_weight))
                
                if current['MR_Short_Signal'] and current['Z_Score'] > 2.0:
                    signal_weight = (current['Range_Weight'] * 1.4 *
                                     current['MR_Signal_Weight'] * regime_multiplier_short)
                    short_signals.append(('Mean Reversion Short', signal_weight))
        
        long_signals = [(signal, weight * volume_multiplier) for signal, weight in long_signals]
        short_signals = [(signal, weight * volume_multiplier) for signal, weight in short_signals]
        
        # Применяем мягкий дневной фильтр
        if 'prohibit_long' in locals() and prohibit_long:
            long_signals = []
        if 'prohibit_short' in locals() and prohibit_short:
            short_signals = []
        long_weight = sum(weight for _, weight in long_signals) / len(long_signals) if long_signals else 0
        short_weight = sum(weight for _, weight in short_signals) / len(short_signals) if short_signals else 0
        
        return {
            'long_signals': long_signals,
            'short_signals': short_signals,
            'long_weight': long_weight,
            'short_weight': short_weight
        }
    def apply_advanced_filtering(self, current, signals):
        long_weight = signals['long_weight']
        short_weight = signals['short_weight']
        
        # Market volatility filter
        atr_ma = current['ATR_MA'] if (current['ATR_MA'] != 0 and not pd.isna(current['ATR_MA'])) else 1e-10
        vol_ratio = current['ATR'] / atr_ma
        
        # --- MR signal boost for low ADX and low volatility ---
        if current['ADX'] < 18 and vol_ratio < 1.3:
            # Boost MR signals in range regime
            for i, (signal, weight) in enumerate(signals.get('long_signals', [])):
                if 'MR_' in signal or 'Mean Reversion' in signal:
                    # Boost to 1.2–1.4 (use 1.3 as average)
                    long_weight = max(long_weight, 1.3)
            for i, (signal, weight) in enumerate(signals.get('short_signals', [])):
                if 'MR_' in signal or 'Mean Reversion' in signal:
                    short_weight = max(short_weight, 1.3)
        
        if vol_ratio > 1.5:
            long_weight *= 0.7
            short_weight *= 0.7
        
        hour = current.name.hour
        if hour >= 0 and hour < 6:
            long_weight *= 0.8
            short_weight *= 0.8
        
        if current['Close'] > current['Open']:
            long_weight *= 1.1
            short_weight *= 0.9
        else:
            long_weight *= 0.9
            short_weight *= 1.1
        
        if hasattr(self, 'trade_df') and self.trade_df is not None and len(self.trade_df) >= 5:
            recent_trades = self.trade_df.tail(5)
            long_trades = recent_trades[recent_trades['position'] == 'LONG']
            short_trades = recent_trades[recent_trades['position'] == 'SHORT']
            
            if len(long_trades) > 0:
                long_win_rate = sum(1 for p in long_trades['pnl'] if p > 0) / len(long_trades)
                if long_win_rate > 0.6:
                    long_weight *= 1.2
                elif long_win_rate < 0.4:
                    long_weight *= 0.8
            
            if len(short_trades) > 0:
                short_win_rate = sum(1 for p in short_trades['pnl'] if p > 0) / len(short_trades)
                if short_win_rate > 0.6:
                    short_weight *= 1.2
                elif short_win_rate < 0.4:
                    short_weight *= 0.8
        
        if 'Final_Long_Bias' in current and 'Final_Short_Bias' in current:
            long_weight *= current['Final_Long_Bias']
            short_weight *= current['Final_Short_Bias']
        
        if 'Market_Regime' in current:
            regime = current['Market_Regime']
            
            if regime == 'strong_bull':
                long_weight *= 1.25
                short_weight *= 0.60      # было 0.65
            elif regime == 'strong_bear':
                long_weight *= 0.80      # было 0.70
                short_weight *= 1.25
            elif regime == 'choppy_range':
                if not any('Mean Reversion' in signal for signal, _ in signals['long_signals']):
                    long_weight *= 0.8
                if not any('Mean Reversion' in signal for signal, _ in signals['short_signals']):
                    short_weight *= 0.8
            elif regime == 'transition_to_bull':
                long_weight *= 1.1
            elif regime == 'transition_to_bear':
                short_weight *= 1.1
        
        # --- Фильтр тренда: запрет шортов в бычьем тренде ---
        if 'Higher_TF_Bullish' in current and current['Higher_TF_Bullish'] and current['Daily_EMA50'] > current['Daily_EMA200']:
            short_weight *= 0.3
        # --- Ребалансировка: если слишком много шортов, почти блокируем их ---
        if hasattr(self, 'trade_df') and self.trade_df is not None and len(self.trade_df) >= 20:
            recent_trades = self.trade_df.tail(20)
            short_ratio = len(recent_trades[recent_trades['position'] == 'SHORT']) / len(recent_trades) if len(recent_trades) > 0 else 0
            if short_ratio > 0.7:
                short_weight *= 0.1
        
        # --- Apply global short penalty ---
        short_weight *= self.params['global_short_penalty']  # Применяем только один раз!
        # --- Apply global long boost ---
        long_weight  *= self.params['global_long_boost']
        # если дневная EMA-50 > EMA-200 и цена выше EMA-50 +- 0.5 % → почти не шортим
        if current['Higher_TF_Bullish'] and current['Close'] > current['Daily_EMA50']*1.005:
            short_weight *= 0.30      # было 0.05
        # --- hot-fix: вернуть агрессию шортам ---
        short_weight *= self.params.get('short_hotfix_multiplier', 1.0)  # теперь параметр
        # --- Trend filter for long ---
        if current['Higher_TF_Bullish'] and current['Daily_EMA50'] > current['Daily_EMA200']:
            long_weight *= 1.3
        else:
            long_weight *= 0.6
        # --- Volume filter for long ---
        if current['Volume_Ratio'] < self.params['volume_threshold']:
            long_weight *= 0.7
        
        return {
            'long_weight': long_weight,
            'short_weight': short_weight
        }
