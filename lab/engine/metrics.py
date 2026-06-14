"""P&L and performance metrics for backtest results."""

from __future__ import annotations
from collections import defaultdict


def compute_metrics(trades: list, starting_cash: float = 50.0, daily_loss_cap: float = 5.0) -> dict:
    """Compute standard performance metrics from a list of trade dicts."""
    if not trades:
        return {
            "trades_executed": 0,
            "net_pnl_dollars": 0.0,
            "net_pnl_pct": 0.0,
            "win_rate": 0.0,
            "breakeven_win_rate": 0.0,
            "edge_over_breakeven_pp": 0.0,
            "avg_return_per_trade": 0.0,
            "max_drawdown_dollars": 0.0,
            "daily_stop_hits": 0,
            "top_2_trade_share_of_gross_profit": 0.0,
        }

    net_pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = wins / len(trades)

    avg_entry = sum(t["entry_price"] for t in trades) / len(trades)
    breakeven_wr = avg_entry  # entry price as fraction = breakeven win rate

    avg_return = net_pnl / len(trades)

    # Max drawdown
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x["game_date"]):
        running += t["pnl"]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    # Top-2 share of gross profit
    profits = sorted([t["pnl"] for t in trades if t["pnl"] > 0], reverse=True)
    gross_profit = sum(profits)
    top2_share = (sum(profits[:2]) / gross_profit) if gross_profit > 0 else 0.0

    # Daily stop hits
    daily_totals = defaultdict(float)
    daily_stop_hits = 0
    for t in sorted(trades, key=lambda x: x["game_date"]):
        daily_totals[t["game_date"]] += t["pnl"]
    for d_pnl in daily_totals.values():
        if d_pnl <= -daily_loss_cap:
            daily_stop_hits += 1

    return {
        "trades_executed": len(trades),
        "net_pnl_dollars": round(net_pnl, 4),
        "net_pnl_pct": round(net_pnl / starting_cash * 100, 2),
        "win_rate": round(win_rate, 4),
        "breakeven_win_rate": round(breakeven_wr, 4),
        "edge_over_breakeven_pp": round((win_rate - breakeven_wr) * 100, 2),
        "avg_return_per_trade": round(avg_return, 4),
        "max_drawdown_dollars": round(max_dd, 4),
        "daily_stop_hits": daily_stop_hits,
        "top_2_trade_share_of_gross_profit": round(top2_share, 4),
    }
