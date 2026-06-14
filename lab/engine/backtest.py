"""
Backtest engine. Runs a single strategy over a list of pre-loaded GameContext records.

For sweep use, call run_on_records() directly rather than instantiating BacktestEngine
for each combo — instantiation overhead adds up at 4000+ combos.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from engine.metrics import compute_metrics
from engine.strategy_base import StrategyBase

RESULTS_DIR = Path(__file__).parent.parent / "results" / "backtests"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class BacktestEngine:
    def __init__(
        self,
        strategy: StrategyBase,
        records: list,
        starting_cash: float = 50.0,
        daily_loss_cap: float = 5.0,
    ):
        self.strategy = strategy
        self.records = records
        self.starting_cash = starting_cash
        self.daily_loss_cap = daily_loss_cap

    def run(self, save: bool = True) -> dict:
        trades = run_on_records(self.strategy, self.records, self.daily_loss_cap)
        metrics = compute_metrics(trades, self.starting_cash, self.daily_loss_cap)

        result = {
            "strategy_id": self.strategy.STRATEGY_ID,
            "params": self.strategy.params,
            "params_hash": _params_hash(self.strategy.params),
            "backtest_date": datetime.datetime.utcnow().isoformat() + "Z",
            "n_records": len(self.records),
            "data_window": {
                "earliest": self.records[0].game_date if self.records else None,
                "latest": self.records[-1].game_date if self.records else None,
            },
            "performance": metrics,
            "trades": trades,
        }

        if save:
            ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            fname = f"{self.strategy.STRATEGY_ID}_{result['params_hash']}_{ts}.json"
            (RESULTS_DIR / fname).write_text(json.dumps(result, indent=2))

        return result


def run_on_records(
    strategy: StrategyBase,
    records: list,
    daily_loss_cap: float = 5.0,
) -> list:
    """Run strategy on records, return list of trade dicts. Fast path for sweeps."""
    trades = []
    daily_pnl: dict = defaultdict(float)

    for ctx in records:
        if daily_pnl[ctx.game_date] <= -daily_loss_cap:
            continue  # daily stop hit

        signal = strategy.generate_signal(ctx)
        if signal is None:
            continue

        buy_a = (signal.buy_team == ctx.team_a)
        entry_price = ctx.mid_a if buy_a else (1.0 - ctx.mid_a)
        settlement = ctx.settlement_a if buy_a else (1.0 - ctx.settlement_a)
        contracts = signal.contracts
        pnl = (settlement - entry_price) * contracts

        daily_pnl[ctx.game_date] += pnl
        trades.append({
            "game_date": ctx.game_date,
            "ticker": ctx.event_ticker,
            "buy_team": signal.buy_team,
            "signal_type": signal.signal_type,
            "strength": signal.strength,
            "entry_price": round(entry_price, 4),
            "contracts": contracts,
            "settlement": round(settlement, 1),
            "pnl": round(pnl, 4),
        })

    return trades


def _params_hash(params: dict) -> str:
    s = json.dumps(params, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:8]
