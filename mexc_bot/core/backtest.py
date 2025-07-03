"""Backtesting utilities for the strategy."""
from typing import Optional
import logging
import pandas as pd

COMMISSION_RATE_ENTRY = 0.00035
COMMISSION_RATE_EXIT = 0.00035


def run_backtest(strategy) -> Optional[pd.DataFrame]:
    """Run the backtest and return results DataFrame"""
    logging.info("Running backtest...")
    balance = strategy.initial_balance
    position = 0
    entry_price = 0.0
    position_size = 0.0
    entry_date = None
    last_trade_date = None
    pyramid_entries = 0
    stop_loss_price = 0.0
    take_profit_price = 0.0
    max_trade_price = 0.0
    min_trade_price = float('inf')
    results = []
    strategy.trade_history = []
    strategy.recent_long_win_rate = 0.5
    strategy.recent_short_win_rate = 0.5
    short_ema = strategy.params['short_ema']
    long_ema = strategy.params['long_ema']
    for i in range(1, len(strategy.data)):
        current = strategy.data.iloc[i]
        previous = strategy.data.iloc[i - 1]
        current_balance = balance
        current_equity = balance
        unrealized_pnl_pct = 0.0
        if position != 0:
            if entry_price <= 0:
                position = 0
                entry_price = 0.0
                position_size = 0.0
                entry_date = None
                pyramid_entries = 0
                max_trade_price = 0.0
                min_trade_price = float('inf')
                continue
            max_trade_price = max(max_trade_price, current['High'])
            min_trade_price = min(min_trade_price, current['Low'])
            trade_age_hours = (current.name - entry_date).total_seconds() / 3600
            higher_tf_bullish = current['Higher_TF_Bullish']
            if position == 1:
                optimal_leverage = strategy.calculate_optimal_leverage(current, 'LONG', strategy.max_leverage)
                unrealized_pnl_pct = (current['Close'] / entry_price) - 1
                unrealized_pnl = unrealized_pnl_pct * position_size
                current_equity = balance + unrealized_pnl
                new_stop = strategy.apply_trailing_stop('LONG', entry_price, current['Close'], max_trade_price, min_trade_price, unrealized_pnl_pct)
                if new_stop is not None and new_stop > stop_loss_price:
                    stop_loss_price = new_stop
                if current['Low'] <= stop_loss_price:
                    pnl = strategy._close_position('LONG', position_size, entry_price, stop_loss_price)
                    balance += pnl
                    strategy.trade_history[-1].update({
                        'exit_date': current.name,
                        'exit_price': stop_loss_price,
                        'pnl': pnl,
                        'balance': balance,
                        'reason': 'Stop Loss',
                        'pyramid_entries': pyramid_entries,
                        'trade_duration': trade_age_hours
                    })
                    strategy._notify_trade_close(strategy.trade_history[-1])
                    position = 0
                    entry_price = 0.0
                    position_size = 0.0
                    entry_date = None
                    last_trade_date = current.name
                    pyramid_entries = 0
                    max_trade_price = 0.0
                    min_trade_price = float('inf')
                    continue
                if current['High'] >= take_profit_price:
                    pnl = strategy._close_position('LONG', position_size, entry_price, take_profit_price)
                    balance += pnl
                    strategy.trade_history[-1].update({
                        'exit_date': current.name,
                        'exit_price': take_profit_price,
                        'pnl': pnl,
                        'balance': balance,
                        'reason': 'Take Profit',
                        'pyramid_entries': pyramid_entries,
                        'trade_duration': trade_age_hours
                    })
                    strategy._notify_trade_close(strategy.trade_history[-1])
                    position = 0
                    entry_price = 0.0
                    position_size = 0.0
                    entry_date = None
                    last_trade_date = current.name
                    pyramid_entries = 0
                    max_trade_price = 0.0
                    min_trade_price = float('inf')
                    continue
                if (
                    pyramid_entries < strategy.params['max_pyramid_entries'] and
                    current['Bullish_Trend'] and
                    current['ADX'] > 40 and
                    current['Close'] > entry_price * (1 + strategy.params['pyramid_min_profit']) and
                    (current['MACD_Bullish_Cross'] or current['Final_Long_Bias'] > 0.7)
                ):
                    additional_size = position_size * strategy.params['pyramid_size_multiplier']
                    old_value = entry_price * position_size
                    new_value = current['Close'] * additional_size
                    position_size += additional_size
                    entry_price = (old_value + new_value) / position_size
                    exit_levels = strategy.calculate_dynamic_exit_levels('LONG', entry_price, current)
                    stop_loss_price = exit_levels['stop_loss']
                    take_profit_price = exit_levels['take_profit']
                    pyramid_entries += 1
                    continue
            if position == -1:
                optimal_leverage = strategy.calculate_optimal_leverage(current, 'SHORT', strategy.max_leverage)
                unrealized_pnl_pct = 1 - (current['Close'] / entry_price)
                unrealized_pnl = unrealized_pnl_pct * position_size
                current_equity = balance + unrealized_pnl
                new_stop = strategy.apply_trailing_stop('SHORT', entry_price, current['Close'], max_trade_price, min_trade_price, unrealized_pnl_pct)
                if new_stop is not None and new_stop < stop_loss_price:
                    stop_loss_price = new_stop
                if current['High'] >= stop_loss_price:
                    pnl = strategy._close_position('SHORT', position_size, entry_price, stop_loss_price)
                    balance += pnl
                    strategy.trade_history[-1].update({
                        'exit_date': current.name,
                        'exit_price': stop_loss_price,
                        'pnl': pnl,
                        'balance': balance,
                        'reason': 'Stop Loss',
                        'pyramid_entries': pyramid_entries,
                        'trade_duration': trade_age_hours
                    })
                    strategy._notify_trade_close(strategy.trade_history[-1])
                    position = 0
                    entry_price = 0.0
                    position_size = 0.0
                    entry_date = None
                    last_trade_date = current.name
                    pyramid_entries = 0
                    max_trade_price = 0.0
                    min_trade_price = float('inf')
                    continue
                if current['Low'] <= take_profit_price:
                    pnl = strategy._close_position('SHORT', position_size, entry_price, take_profit_price)
                    balance += pnl
                    strategy.trade_history[-1].update({
                        'exit_date': current.name,
                        'exit_price': take_profit_price,
                        'pnl': pnl,
                        'balance': balance,
                        'reason': 'Take Profit',
                        'pyramid_entries': pyramid_entries,
                        'trade_duration': trade_age_hours
                    })
                    strategy._notify_trade_close(strategy.trade_history[-1])
                    position = 0
                    entry_price = 0.0
                    position_size = 0.0
                    entry_date = None
                    last_trade_date = current.name
                    pyramid_entries = 0
                    max_trade_price = 0.0
                    min_trade_price = float('inf')
                    continue
                if (
                    pyramid_entries < strategy.params['max_pyramid_entries'] and
                    current['Bearish_Trend'] and
                    current['ADX'] > 40 and
                    current['Close'] < entry_price * (1 - strategy.params['pyramid_min_profit']) and
                    (current['MACD_Bearish_Cross'] or current['Final_Short_Bias'] > 0.7)
                ):
                    additional_size = position_size * strategy.params['pyramid_size_multiplier']
                    old_value = entry_price * position_size
                    new_value = current['Close'] * additional_size
                    position_size += additional_size
                    balance -= additional_size * COMMISSION_RATE_ENTRY
                    entry_price = (old_value + new_value) / position_size
                    exit_levels = strategy.calculate_dynamic_exit_levels('SHORT', entry_price, current)
                    stop_loss_price = exit_levels['stop_loss']
                    take_profit_price = exit_levels['take_profit']
                    pyramid_entries += 1
                    continue
        regime = 'trend' if current['Trend_Weight'] > 0.5 else 'range'
        trading_signals = strategy.get_trading_signals(current, previous, regime)
        filtered = strategy.apply_advanced_filtering(current, trading_signals)
        long_ok = filtered['long_weight'] >= 0.65 and filtered['long_weight'] > filtered['short_weight']
        short_ok = filtered['short_weight'] >= 0.65 and filtered['short_weight'] > filtered['long_weight']
        if long_ok and position == 0 and strategy.check_entry_cooldown(last_trade_date, current.name):
            exit_levels = strategy.calculate_dynamic_exit_levels('LONG', current['Close'], current)
            position_size = strategy.calculate_position_size(balance, exit_levels['stop_loss'], current['Close'])
            position = 1
            entry_price = current['Close']
            entry_date = current.name
            stop_loss_price = exit_levels['stop_loss']
            take_profit_price = exit_levels['take_profit']
            balance -= position_size * COMMISSION_RATE_ENTRY
            strategy.trade_history.append({
                'entry_date': current.name,
                'position': 'LONG',
                'entry_price': entry_price,
                'position_size': position_size,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'weight': filtered['long_weight'],
                'market_regime': filtered['market_regime'],
                'exit_date': None,
                'exit_price': None,
                'pnl': None,
                'balance': balance,
                'trade_duration': None,
            })
            strategy._notify_trade_open(strategy.trade_history[-1])
            strategy.current_side = 'LONG'
            continue
        if short_ok and position == 0 and strategy.check_entry_cooldown(last_trade_date, current.name):
            exit_levels = strategy.calculate_dynamic_exit_levels('SHORT', current['Close'], current)
            position_size = strategy.calculate_position_size(balance, exit_levels['stop_loss'], current['Close'])
            position = -1
            entry_price = current['Close']
            entry_date = current.name
            stop_loss_price = exit_levels['stop_loss']
            take_profit_price = exit_levels['take_profit']
            balance -= position_size * COMMISSION_RATE_ENTRY
            strategy.trade_history.append({
                'entry_date': current.name,
                'position': 'SHORT',
                'entry_price': entry_price,
                'position_size': position_size,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'weight': filtered['short_weight'],
                'market_regime': filtered['market_regime'],
                'exit_date': None,
                'exit_price': None,
                'pnl': None,
                'balance': balance,
                'trade_duration': None,
            })
            strategy._notify_trade_open(strategy.trade_history[-1])
            strategy.current_side = 'SHORT'
            continue
        current_equity = balance
        if position != 0:
            if position == 1:
                current_equity = balance + position_size * ((current['Close'] / entry_price) - 1)
            elif position == -1:
                current_equity = balance + position_size * (1 - (current['Close'] / entry_price))
        results.append({
            'date': current.name,
            'balance': balance,
            'equity': current_equity,
            'position': position,
            'price': current['Close'],
            'market_health': current.get('Market_Health', None),
            'market_regime': regime,
        })
        if len(strategy.trade_history) % 20 == 0 and len(strategy.trade_history) > 0:
            strategy.dynamically_adjust_risk_parameters()
        if i % 672 == 0 and len(strategy.trade_history) > 30:
            strategy.rebalance_long_short_bias()
        if position == 1 and 'unrealized_pnl_pct' in locals() and unrealized_pnl_pct > 0.12 and position_size > 0:
            partial_size = position_size * 0.4
            partial_pnl = partial_size * ((current['Close'] / entry_price) - 1)
            commission = partial_size * COMMISSION_RATE_EXIT
            slippage = partial_size * strategy.slippage_pct / 100
            partial_pnl -= (commission + slippage)
            balance += partial_pnl
            position_size -= partial_size
        if position == -1 and 'unrealized_pnl_pct' in locals() and unrealized_pnl_pct > 0.12 and position_size > 0:
            partial_size = position_size * 0.4
            partial_pnl = partial_size * (1 - (current['Close'] / entry_price))
            commission = partial_size * COMMISSION_RATE_EXIT
            slippage = partial_size * strategy.slippage_pct / 100
            partial_pnl -= (commission + slippage)
            balance += partial_pnl
            position_size -= partial_size
        if (
            position == 1 and
            pyramid_entries < strategy.params['max_pyramid_entries'] and
            current['Bullish_Trend'] and
            current['ADX'] > 30 and
            current['Close'] > entry_price * (1 + 0.02) and
            (current['MACD_Bullish_Cross'] or current['Final_Long_Bias'] > 0.65)
        ):
            additional_size = position_size * strategy.params['pyramid_size_multiplier']
            old_value = entry_price * position_size
            new_value = current['Close'] * additional_size
            position_size += additional_size
            balance -= additional_size * COMMISSION_RATE_ENTRY
            entry_price = (old_value + new_value) / position_size
            exit_levels = strategy.calculate_dynamic_exit_levels('LONG', entry_price, current)
            stop_loss_price = exit_levels['stop_loss']
            take_profit_price = exit_levels['take_profit']
            pyramid_entries += 1
            continue
    if position != 0 and entry_price > 0:
        last_candle = strategy.data.iloc[-1]
        exit_price = last_candle['Close']
        trade_age_hours = (last_candle.name - entry_date).total_seconds() / 3600
        if position == 1:
            pnl = strategy._close_position('LONG', position_size, entry_price, exit_price)
        else:
            pnl = strategy._close_position('SHORT', position_size, entry_price, exit_price)
        balance += pnl
        for trade in reversed(strategy.trade_history):
            if trade['exit_date'] is None:
                trade['exit_date'] = last_candle.name
                trade['exit_price'] = exit_price
                trade['pnl'] = pnl
                trade['balance'] = balance
                trade['reason'] = trade['reason'] + ', End of Backtest'
                trade['trade_duration'] = trade_age_hours
                break
    strategy.current_side = None
    strategy.backtest_results = pd.DataFrame(results)
    if strategy.trade_history:
        strategy.trade_df = pd.DataFrame(strategy.trade_history)
        strategy.trade_df['exit_date'].fillna(strategy.data.index[-1], inplace=True)
        strategy.trade_df['exit_price'].fillna(strategy.data['Close'].iloc[-1], inplace=True)
        mask = strategy.trade_df['pnl'].isna()
        strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'LONG'), 'pnl'] = (
            strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'LONG'), 'position_size'] *
            (strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'LONG'), 'exit_price'] /
             strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'LONG'), 'entry_price'] - 1)
        )
        strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'SHORT'), 'pnl'] = (
            strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'SHORT'), 'position_size'] *
            (1 - strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'SHORT'), 'exit_price'] /
             strategy.trade_df.loc[mask & (strategy.trade_df['position'] == 'SHORT'), 'entry_price'])
        )
    else:
        strategy.trade_df = pd.DataFrame()
    strategy.analyze_hour_performance()
    strategy.analyze_day_performance()
    logging.info("Backtest completed")
    return strategy.backtest_results
