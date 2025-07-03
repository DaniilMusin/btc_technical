"""Plotting utilities for strategy results."""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import pandas as pd
from loguru import logger


def plot_equity_curve(strategy):
    if strategy.backtest_results is None:
        logger.warning("No backtest results available. Run backtest first.")
        return
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [3, 1, 1]})
    ax1.plot(strategy.backtest_results['date'], strategy.backtest_results['equity'], label='Equity', color='blue')
    ax1.plot(strategy.backtest_results['date'], strategy.backtest_results['balance'], label='Balance', color='green')
    equity_curve = strategy.backtest_results['equity']
    running_max = equity_curve.cummax()
    drawdown = (running_max - equity_curve) / running_max * 100
    ax2.fill_between(strategy.backtest_results['date'], 0, drawdown, color='red', alpha=0.3)
    ax2.set_ylim(bottom=0, top=max(drawdown) * 1.5)
    ax2.invert_yaxis()
    if 'market_health' in strategy.backtest_results.columns and not strategy.backtest_results['market_health'].isnull().all():
        ax3.plot(strategy.backtest_results['date'], strategy.backtest_results['market_health'], label='Market Health', color='purple', alpha=0.7)
        ax3.set_ylim(bottom=0, top=100)
        ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
        ax3.set_title('Market Health Score (0-100)')
    else:
        if 'market_regime' in strategy.backtest_results.columns and not strategy.backtest_results['market_regime'].isnull().all():
            regime_indicator = strategy.backtest_results['market_regime'].map({
                'strong_bull': 1.0,
                'transition_to_bull': 0.5,
                'choppy_range': 0,
                'transition_to_bear': -0.5,
                'strong_bear': -1.0,
                'mixed': 0,
                'unknown': pd.NA
            }).fillna(0)
            ax3.plot(strategy.backtest_results['date'], regime_indicator, label='Market Regime', color='orange', alpha=0.7)
            ax3.set_ylim(bottom=-1.2, top=1.2)
            ax3.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax3.set_title('Market Regime (1=Bull, 0=Range, -1=Bear)')
    date_format = mdates.DateFormatter('%Y-%m-%d')
    ax1.xaxis.set_major_formatter(date_format)
    ax2.xaxis.set_major_formatter(date_format)
    ax3.xaxis.set_major_formatter(date_format)
    def currency_formatter(x, pos):
        return f'${x:,.0f}'
    ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    def percentage_formatter(x, pos):
        return f'{x:.0f}%'
    ax2.yaxis.set_major_formatter(FuncFormatter(percentage_formatter))
    initial_balance = strategy.initial_balance
    final_balance = strategy.backtest_results['balance'].iloc[-1]
    total_return = ((final_balance / initial_balance) - 1) * 100
    max_drawdown_val = drawdown.max()
    if hasattr(strategy, 'trade_df') and strategy.trade_df is not None and len(strategy.trade_df) > 0:
        win_rate = len(strategy.trade_df[strategy.trade_df['pnl'] > 0]) / len(strategy.trade_df) * 100
    else:
        win_rate = 0
    textstr = '\n'.join((
        f'Initial Balance: ${initial_balance:,.2f}',
        f'Final Balance: ${final_balance:,.2f}',
        f'Total Return: {total_return:.2f}%',
        f'Max Drawdown: {max_drawdown_val:.2f}%',
        f'Win Rate: {win_rate:.2f}%',
        f'Total Trades: {len(strategy.trade_df) if hasattr(strategy, "trade_df") else 0}'
    ))
    props = dict(boxstyle='round', facecolor='white', alpha=0.5)
    ax1.text(0.02, 0.05, textstr, transform=ax1.transAxes, fontsize=10, verticalalignment='bottom', bbox=props)
    if hasattr(strategy, 'trade_df') and len(strategy.trade_df) > 0:
        sample_trades = strategy.trade_df.sample(min(50, len(strategy.trade_df))) if len(strategy.trade_df) > 50 else strategy.trade_df
        for _, trade in sample_trades.iterrows():
            color = 'green' if trade['position'] == 'LONG' else 'red'
            marker = '^' if trade['position'] == 'LONG' else 'v'
            entry_date = pd.to_datetime(trade['entry_date'])
            exit_date = pd.to_datetime(trade['exit_date'])
            closest_entry = min(strategy.backtest_results['date'], key=lambda x: abs(x - entry_date))
            entry_equity = strategy.backtest_results.loc[strategy.backtest_results['date'] == closest_entry, 'equity'].values
            if len(entry_equity) > 0:
                ax1.scatter(closest_entry, entry_equity[0], color=color, s=50, marker=marker, alpha=0.6)
            closest_exit = min(strategy.backtest_results['date'], key=lambda x: abs(x - exit_date))
            exit_equity = strategy.backtest_results.loc[strategy.backtest_results['date'] == closest_exit, 'equity'].values
            if len(exit_equity) > 0:
                ax1.scatter(closest_exit, exit_equity[0], color='black', s=30, marker='o', alpha=0.6)
    ax1.set_title('Equity Curve and Performance')
    ax1.set_ylabel('Account Value')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax2.set_title('Drawdown')
    ax2.set_ylabel('Drawdown (%)')
    ax2.grid(True, alpha=0.3)
    ax3.grid(True, alpha=0.3)
    ax3.legend()
    plt.tight_layout()
    plt.show()
    return fig


def plot_regime_performance(strategy):
    if not hasattr(strategy, 'trade_df') or len(strategy.trade_df) == 0 or 'market_regime' not in strategy.trade_df.columns:
        logger.warning("No regime data available.")
        return
    regime_stats = strategy.trade_df.groupby('market_regime').agg({
        'pnl': ['count', 'mean', 'sum'],
        'position': 'count'
    }).reset_index()
    regime_stats.columns = ['regime', 'num_trades', 'avg_pnl', 'total_pnl', 'position_count']
    regime_win_rates = []
    for regime in regime_stats['regime'].unique():
        regime_trades = strategy.trade_df[strategy.trade_df['market_regime'] == regime]
        wins = sum(1 for pnl in regime_trades['pnl'] if pnl > 0)
        total = len(regime_trades)
        win_rate = wins / total if total > 0 else 0
        regime_win_rates.append(win_rate * 100)
    regime_stats['win_rate'] = regime_win_rates
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5))
    regime_colors = {
        'strong_bull': 'green',
        'transition_to_bull': 'lightgreen',
        'choppy_range': 'gray',
        'transition_to_bear': 'salmon',
        'strong_bear': 'red',
        'mixed': 'blue',
        'unknown': 'lightgray'
    }
    bars1 = ax1.bar(regime_stats['regime'], regime_stats['num_trades'], color=[regime_colors.get(r, 'gray') for r in regime_stats['regime']])
    ax1.set_title('Number of Trades by Market Regime')
    ax1.set_xlabel('Market Regime')
    ax1.set_ylabel('Number of Trades')
    for bar in bars1:
        height = bar.get_height()
        ax1.annotate(f'{height}', xy=(bar.get_x() + bar.get_width() / 2, height), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    bars2 = ax2.bar(regime_stats['regime'], regime_stats['win_rate'], color=[regime_colors.get(r, 'gray') for r in regime_stats['regime']])
    ax2.set_title('Win Rate by Market Regime')
    ax2.set_xlabel('Market Regime')
    ax2.set_ylabel('Win Rate (%)')
    ax2.set_ylim(0, 100)
    for bar in bars2:
        height = bar.get_height()
        ax2.annotate(f'{height:.1f}%', xy=(bar.get_x() + bar.get_width() / 2, height), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    bars3 = ax3.bar(regime_stats['regime'], regime_stats['total_pnl'], color=[regime_colors.get(r, 'gray') for r in regime_stats['regime']])
    ax3.set_title('Total P&L by Market Regime')
    ax3.set_xlabel('Market Regime')
    ax3.set_ylabel('P&L ($)')
    for bar in bars3:
        height = bar.get_height()
        ax3.annotate(f'${height:.1f}', xy=(bar.get_x() + bar.get_width() / 2, height), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
    plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
    plt.setp(ax3.get_xticklabels(), rotation=45, ha='right')
    plt.tight_layout()
    plt.show()
    return fig
