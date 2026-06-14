# strategy_lab

Parameter sweep and backtest engine for agenticagent's Kalshi MLB trading strategies.

## Purpose

Evaluate whether a strategy has edge at ANY parameter setting, not just at defaults. Wide sweeps across full grids with train/test holdout prevent overfit results from entering the paper trial.

## Structure

```
strategy_lab/
├── engine/
│   ├── backtest.py          # Single-run backtest (BacktestEngine)
│   ├── data_loader.py       # Orderbook DB + MLB API with SQLite caching
│   ├── metrics.py           # P&L, win rate, edge, max drawdown, top-2 share
│   ├── sweep.py             # Parameter sweep with 70/30 train/test split
│   ├── strategy_base.py     # Abstract base class (Signal, GameContext, StrategyBase)
│   └── cluster_analysis.py  # Per-parameter cluster averaging for robustness
├── strategies/
│   └── mm2_v1.py            # Parameterized MM-2 (recency bias)
├── cache/
│   └── recent_form_cache.db # Cached MLB schedule data (don't delete)
├── results/
│   ├── backtests/           # Individual backtest JSON files
│   └── sweeps/              # Sweep result JSON + markdown reports
└── cli.py
```

## Quick start

```bash
cd ~/.openclaw/workspace/strategy_lab

# Single backtest at default params
python3 cli.py backtest --strategy mm2_v1

# Single backtest with param overrides
python3 cli.py backtest --strategy mm2_v1 --params 'recent_form_window=7,implied_prob_low_threshold=0.30'

# Full wide sweep (5,760 combos, ~2 min total with cache warm)
python3 cli.py sweep --strategy mm2_v1

# Compare top combos from a sweep
python3 cli.py compare --results results/sweeps/mm2_v1_20260614T052720.json

# Cluster analysis
python3 cli.py cluster --results results/sweeps/mm2_v1_20260614T052720.json

# List strategies
python3 cli.py list-strategies
```

## Sweep methodology

1. Build all coherent parameter combinations (coherence filter: low_threshold < high_threshold)
2. Pre-load ALL data into memory (orderbook prices + cached team schedules + outcomes)
3. Sort records chronologically; split 70% train / 30% holdout
4. Run all combos on train window
5. Cluster analysis: per-parameter average P&L to identify which parameters drive results
6. Identify top 50 by train P&L; run holdout sweep
7. Report: how many of top 50 pass ALL holdout criteria?

Holdout pass criteria (all must hold): P&L > $0, win rate > breakeven + 2pp, trades ≥ 20, max drawdown < $10.

## Adding a new strategy

1. Subclass `StrategyBase` in `strategies/my_strategy.py`
2. Implement `DEFAULT_PARAMS`, `STRATEGY_ID`, `generate_signal()`
3. Register in `cli.py`'s `_load_strategies()`

## Results archive

| Sweep | Date | Combos | Train best | Holdout candidates | Verdict |
|---|---|---|---|---|---|
| mm2_v1 wide | 2026-06-14 | 5,760 | $+13.08 (overfit) | 0 / 50 | NULL RESULT |

## Performance notes

- Cache warm (MLB API, 29 teams): ~23s one-time
- Subsequent runs (from cache): ~1-2s load + ~2s for 5,760 combos
- Data is pre-loaded into memory; no DB hits during sweep
