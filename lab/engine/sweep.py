"""
Parameter sweep harness with train/test split and holdout validation.

Execution order:
1. Coherence filter: prune param combos that violate strategy invariants
2. Train sweep: all coherent combos on first 70% of records
3. Cluster analysis on train results
4. Identify top 50 combos by train P&L
5. Holdout sweep: top 50 on last 30% of records
6. Report holdout edge confirmation
"""

from __future__ import annotations

import datetime
import itertools
import json
import time
from pathlib import Path

from engine.backtest import run_on_records
from engine.cluster_analysis import analyze_clusters
from engine.metrics import compute_metrics

SWEEPS_DIR = Path(__file__).parent.parent / "results" / "sweeps"
SWEEPS_DIR.mkdir(parents=True, exist_ok=True)

# Holdout pass criteria (ALL must hold)
HOLDOUT_MIN_TRADES = 20
HOLDOUT_MIN_EDGE_PP = 2.0        # win_rate > breakeven + 2pp
HOLDOUT_MAX_DRAWDOWN = 10.0      # dollars
DAILY_LOSS_CAP = 5.0
STARTING_CASH = 50.0


def _coherence_check(params: dict) -> tuple[bool, str]:
    """Return (passes, reason). Prune combos that are logically invalid."""
    if params["implied_prob_low_threshold"] >= params["implied_prob_high_threshold"]:
        return False, "low_threshold >= high_threshold"
    return True, ""


def _build_combos(param_grid: dict) -> list:
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combos = []
    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        ok, _ = _coherence_check(params)
        if ok:
            combos.append(params)
    return combos


def sweep(
    strategy_class,
    param_grid: dict,
    records: list,
    top_n: int = 50,
    verbose: bool = True,
) -> dict:
    """Run full sweep with train/test split. Returns aggregated results dict."""
    t0 = time.time()
    if verbose:
        print(f"\n[sweep] Building parameter combinations...")

    all_combos = _build_combos(param_grid)
    naive_count = 1
    for v in param_grid.values():
        naive_count *= len(v)

    if verbose:
        print(f"[sweep] Naive: {naive_count} → After coherence filter: {len(all_combos)}")

    # Train/test split (70/30 chronological)
    split_idx = int(len(records) * 0.70)
    train_records = records[:split_idx]
    test_records = records[split_idx:]

    if verbose:
        train_start = train_records[0].game_date if train_records else "N/A"
        train_end = train_records[-1].game_date if train_records else "N/A"
        test_start = test_records[0].game_date if test_records else "N/A"
        test_end = test_records[-1].game_date if test_records else "N/A"
        print(f"[sweep] Train: {len(train_records)} records ({train_start} to {train_end})")
        print(f"[sweep] Test:  {len(test_records)} records ({test_start} to {test_end})")

    # ── Train sweep ────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n[sweep] Running {len(all_combos)} combos on train set...")
    train_results = []
    report_interval = max(1, len(all_combos) // 10)

    for i, params in enumerate(all_combos):
        if verbose and i % report_interval == 0:
            pct = i / len(all_combos) * 100
            print(f"[sweep]   {i}/{len(all_combos)} ({pct:.0f}%)", end="\r", flush=True)

        strategy = strategy_class(params)
        trades = run_on_records(strategy, train_records, DAILY_LOSS_CAP)
        metrics = compute_metrics(trades, STARTING_CASH, DAILY_LOSS_CAP)
        train_results.append({"params": params, "metrics": metrics, "n_trades": len(trades)})

    train_elapsed = time.time() - t0
    if verbose:
        print(f"\n[sweep] Train sweep complete ({train_elapsed:.1f}s)")

    # Sort by train P&L
    train_results.sort(key=lambda r: r["metrics"]["net_pnl_dollars"], reverse=True)

    # ── Cluster analysis ───────────────────────────────────────────────────────
    param_names = list(param_grid.keys())
    cluster_report = analyze_clusters(train_results, param_names)

    # ── Holdout sweep (top N by train P&L) ────────────────────────────────────
    top_combos = train_results[:top_n]
    if verbose:
        print(f"\n[sweep] Running holdout on top {len(top_combos)} combos...")

    holdout_results = []
    for entry in top_combos:
        strategy = strategy_class(entry["params"])
        trades = run_on_records(strategy, test_records, DAILY_LOSS_CAP)
        metrics = compute_metrics(trades, STARTING_CASH, DAILY_LOSS_CAP)
        passes = _holdout_passes(metrics)
        holdout_results.append({
            "params": entry["params"],
            "train_metrics": entry["metrics"],
            "test_metrics": metrics,
            "holdout_passes": passes,
        })

    # Sort holdout by test P&L
    holdout_results.sort(key=lambda r: r["test_metrics"]["net_pnl_dollars"], reverse=True)

    candidates = [r for r in holdout_results if r["holdout_passes"]]
    holdout_elapsed = time.time() - t0

    if verbose:
        print(f"[sweep] Holdout complete. Candidates: {len(candidates)}/{len(holdout_results)}")

    # ── Distribution stats ─────────────────────────────────────────────────────
    all_pnls = [r["metrics"]["net_pnl_dollars"] for r in train_results]
    positive_pnl_count = sum(1 for p in all_pnls if p > 0)
    pnl_mean = sum(all_pnls) / len(all_pnls) if all_pnls else 0
    pnl_std = (sum((p - pnl_mean) ** 2 for p in all_pnls) / len(all_pnls)) ** 0.5 if len(all_pnls) > 1 else 0

    result = {
        "sweep_id": f"{strategy_class.STRATEGY_ID}_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}",
        "strategy_id": strategy_class.STRATEGY_ID,
        "sweep_date": datetime.datetime.utcnow().isoformat() + "Z",
        "param_grid": param_grid,
        "combos": {
            "naive_count": naive_count,
            "coherent_count": len(all_combos),
            "pruned_count": naive_count - len(all_combos),
        },
        "split": {
            "train_records": len(train_records),
            "test_records": len(test_records),
            "split_pct": 70,
        },
        "train": {
            "elapsed_seconds": round(train_elapsed, 1),
            "top_n": train_results[:top_n],
            "pnl_distribution": {
                "mean": round(pnl_mean, 4),
                "std": round(pnl_std, 4),
                "min": round(min(all_pnls), 4),
                "max": round(max(all_pnls), 4),
                "median": round(sorted(all_pnls)[len(all_pnls) // 2], 4),
                "positive_count": positive_pnl_count,
                "negative_count": len(all_pnls) - positive_pnl_count,
                "total_combos": len(all_pnls),
            },
        },
        "cluster_analysis": cluster_report,
        "holdout": {
            "top_n_tested": len(top_combos),
            "candidates_found": len(candidates),
            "elapsed_seconds": round(holdout_elapsed, 1),
            "results": holdout_results,
            "candidates": candidates,
        },
        "criteria": {
            "holdout_min_trades": HOLDOUT_MIN_TRADES,
            "holdout_min_edge_pp": HOLDOUT_MIN_EDGE_PP,
            "holdout_max_drawdown": HOLDOUT_MAX_DRAWDOWN,
        },
    }

    # Save JSON
    fname = f"{result['sweep_id']}.json"
    out_path = SWEEPS_DIR / fname
    out_path.write_text(json.dumps(result, indent=2))
    if verbose:
        print(f"[sweep] Results saved → {out_path}")

    return result


def _holdout_passes(metrics: dict) -> bool:
    if metrics["trades_executed"] < HOLDOUT_MIN_TRADES:
        return False
    if metrics["net_pnl_dollars"] <= 0:
        return False
    if metrics["edge_over_breakeven_pp"] < HOLDOUT_MIN_EDGE_PP:
        return False
    if metrics["max_drawdown_dollars"] > HOLDOUT_MAX_DRAWDOWN:
        return False
    return True
