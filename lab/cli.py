#!/usr/bin/env python3
"""
Strategy Lab CLI

Usage:
  python3 cli.py backtest --strategy mm2_v1 --params 'recent_form_window=5'
  python3 cli.py sweep --strategy mm2_v1 --grid sweep_configs/mm2_v1_wide.yaml
  python3 cli.py compare --results results/sweeps/{sweep_id}.json
  python3 cli.py cluster --results results/sweeps/{sweep_id}.json
  python3 cli.py list-strategies
"""

import argparse
import json
import sys
from pathlib import Path

# Add lab root to path so engine/ and strategies/ are importable
sys.path.insert(0, str(Path(__file__).parent))

from engine.data_loader import DataLoader
from engine.backtest import BacktestEngine

LAB_ROOT = Path(__file__).parent
CACHE_DB = LAB_ROOT / "cache" / "recent_form_cache.db"
CACHE_DB.parent.mkdir(exist_ok=True)

STRATEGY_MAP = {}

def _load_strategies():
    from strategies.mm2_v1 import MM2V1
    STRATEGY_MAP["mm2_v1"] = MM2V1


def _get_strategy_class(name: str):
    _load_strategies()
    if name not in STRATEGY_MAP:
        print(f"ERROR: Unknown strategy '{name}'. Available: {list(STRATEGY_MAP.keys())}")
        sys.exit(1)
    return STRATEGY_MAP[name]


def _load_records(verbose: bool = True):
    loader = DataLoader(CACHE_DB)
    loader.warm_cache(verbose=verbose)
    records, excl = loader.load_game_records(verbose=verbose)
    loader.close()
    return records


def _parse_params(params_str: str) -> dict:
    """Parse 'key=val,key=val' string into dict with type coercion."""
    result = {}
    for pair in params_str.split(','):
        pair = pair.strip()
        if '=' not in pair:
            continue
        k, v = pair.split('=', 1)
        k = k.strip(); v = v.strip()
        try:
            result[k] = int(v)
        except ValueError:
            try:
                result[k] = float(v)
            except ValueError:
                result[k] = v
    return result


def cmd_backtest(args):
    strategy_class = _get_strategy_class(args.strategy)
    params = _parse_params(args.params) if args.params else {}

    print(f"[backtest] Strategy: {args.strategy} params: {params}")
    records = _load_records()
    strategy = strategy_class(params)
    engine = BacktestEngine(strategy, records)
    result = engine.run(save=True)
    p = result["performance"]
    print(f"\n{'='*50}")
    print(f"BACKTEST: {args.strategy} {params}")
    print(f"Trades:     {p['trades_executed']}")
    print(f"Net P&L:    ${p['net_pnl_dollars']:.2f} ({p['net_pnl_pct']:.1f}% of $50)")
    print(f"Win rate:   {p['win_rate']:.1%} vs breakeven {p['breakeven_win_rate']:.1%}")
    print(f"Edge:       {p['edge_over_breakeven_pp']:+.2f}pp")
    print(f"Max DD:     ${p['max_drawdown_dollars']:.2f}")
    print(f"Daily stops:{p['daily_stop_hits']}")
    print(f"Top-2 share:{p['top_2_trade_share_of_gross_profit']:.1%}")


def cmd_sweep(args):
    from engine.sweep import sweep

    strategy_class = _get_strategy_class(args.strategy)

    # Load grid from YAML or use built-in default
    if args.grid and Path(args.grid).exists():
        try:
            import yaml
            with open(args.grid) as f:
                param_grid = yaml.safe_load(f)
        except ImportError:
            print("ERROR: PyYAML not installed. Use built-in grid or pip install pyyaml")
            sys.exit(1)
    else:
        # Built-in wide grid for mm2_v1
        param_grid = {
            "recent_form_window": [3, 5, 7, 10, 15, 20],
            "recent_form_wins_fraction": [0.50, 0.60, 0.70, 0.80],
            "implied_prob_low_threshold": [0.20, 0.30, 0.40, 0.50],
            "implied_prob_high_threshold": [0.55, 0.65, 0.75, 0.85],
            "signal_strength_threshold": [40, 50, 60, 70, 80],
            "max_contracts": [1, 3, 5],
        }
        print("[sweep] Using built-in mm2_v1 wide grid")

    records = _load_records()

    # Validate signals at default params vs signal_generator.py
    if args.strategy == "mm2_v1":
        strategy_class.validate_vs_signal_generator(records)

    result = sweep(strategy_class, param_grid, records)

    h = result["holdout"]
    t = result["train"]["pnl_distribution"]
    print(f"\n{'='*60}")
    print(f"SWEEP COMPLETE: {result['combos']['coherent_count']} combos")
    print(f"Train P&L dist: mean=${t['mean']:.2f} median=${t['median']:.2f} std=${t['std']:.2f}")
    print(f"Positive train combos: {t['positive_count']}/{t['total_combos']}")
    print(f"Candidates (holdout pass): {h['candidates_found']}/{h['top_n_tested']}")
    if h["candidates"]:
        best = h["candidates"][0]
        print(f"Best candidate: P&L={best['test_metrics']['net_pnl_dollars']:.2f} "
              f"edge={best['test_metrics']['edge_over_breakeven_pp']:+.2f}pp params={best['params']}")
    print(f"Results → {result['sweep_id']}.json")


def cmd_compare(args):
    path = Path(args.results)
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)
    data = json.loads(path.read_text())
    top = data.get("train", {}).get("top_n", [])[:20]
    print(f"\nTop 20 train combos — {path.name}")
    print(f"{'Rank':<5} {'P&L':>7} {'WinRate':>8} {'Edge':>7} {'Trades':>7} {'Params'}")
    print("-" * 90)
    for i, r in enumerate(top, 1):
        m = r["metrics"]
        params_short = {k: v for k, v in r["params"].items()}
        print(f"{i:<5} ${m['net_pnl_dollars']:>6.2f} {m['win_rate']:>8.1%} "
              f"{m['edge_over_breakeven_pp']:>+6.1f}pp {m['trades_executed']:>7}  {params_short}")


def cmd_cluster(args):
    path = Path(args.results)
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)
    data = json.loads(path.read_text())
    cluster = data.get("cluster_analysis", {})
    per_param = cluster.get("per_parameter", {})
    top_spread = cluster.get("top_50_spread", {})

    print(f"\nCluster Analysis — {path.name}")
    print("=" * 60)
    print(f"\nPer-parameter cluster averages (which parameters drive P&L?):")
    for pname, info in per_param.items():
        print(f"\n  {pname} [{info['signal']}] — P&L range across values: ${info['pnl_range']:.2f}")
        print(f"  Best value: {info['best_value']}")
        for val, stats in info["cluster_averages"].items():
            print(f"    {val:>10}: avg P&L ${stats['avg_pnl']:>7.2f}  ({stats['count']} combos)")

    print(f"\nTop 50 combos — parameter spread:")
    for pname, info in top_spread.items():
        print(f"  {pname}: {info['unique_count']} unique values {info['unique_values']} mode={info['mode']}")

    interp = cluster.get("interpretation", {})
    print(f"\nVerdict: {interp.get('overall', 'N/A')}")


def cmd_list_strategies(args):
    _load_strategies()
    print("Available strategies:")
    for name, cls in STRATEGY_MAP.items():
        print(f"  {name}: {cls.__doc__.strip().splitlines()[0] if cls.__doc__ else '(no docstring)'}")


def main():
    parser = argparse.ArgumentParser(description="Strategy Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bt = subparsers.add_parser("backtest", help="Run single backtest")
    bt.add_argument("--strategy", required=True)
    bt.add_argument("--params", default="", help="key=val,key=val overrides")
    bt.set_defaults(func=cmd_backtest)

    sw = subparsers.add_parser("sweep", help="Run parameter sweep")
    sw.add_argument("--strategy", required=True)
    sw.add_argument("--grid", default="", help="Path to YAML grid config")
    sw.set_defaults(func=cmd_sweep)

    cmp = subparsers.add_parser("compare", help="Compare sweep results")
    cmp.add_argument("--results", required=True)
    cmp.set_defaults(func=cmd_compare)

    cl = subparsers.add_parser("cluster", help="Show cluster analysis")
    cl.add_argument("--results", required=True)
    cl.set_defaults(func=cmd_cluster)

    ls = subparsers.add_parser("list-strategies", help="List available strategies")
    ls.set_defaults(func=cmd_list_strategies)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
