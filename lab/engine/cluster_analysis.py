"""
Cluster analysis: for each parameter, compute average metrics across all combos
where that parameter is fixed at a given value. Identifies which parameters
drive performance vs which are noise.
"""

from __future__ import annotations
from collections import defaultdict


def analyze_clusters(train_results: list, param_names: list) -> dict:
    """
    For each parameter, compute average train P&L and average edge across
    all combinations where that parameter takes each distinct value.

    Also analyzes the top 50 combos: are they clustered in parameter space
    (real pattern) or scattered (noise)?

    Returns a report dict.
    """
    # Per-parameter cluster averages
    per_param = {}
    for pname in param_names:
        value_groups: dict = defaultdict(list)
        for r in train_results:
            val = r["params"].get(pname)
            if val is not None:
                value_groups[val].append(r["metrics"]["net_pnl_dollars"])

        cluster_avgs = {}
        for val, pnls in sorted(value_groups.items()):
            cluster_avgs[str(val)] = {
                "avg_pnl": round(sum(pnls) / len(pnls), 4),
                "count": len(pnls),
            }

        # Range of averages — small range = parameter doesn't matter
        avg_vals = [v["avg_pnl"] for v in cluster_avgs.values()]
        pnl_range = max(avg_vals) - min(avg_vals) if len(avg_vals) > 1 else 0
        best_val = max(cluster_avgs.items(), key=lambda x: x[1]["avg_pnl"])[0] if cluster_avgs else None

        per_param[pname] = {
            "cluster_averages": cluster_avgs,
            "pnl_range": round(pnl_range, 4),
            "best_value": best_val,
            "signal": _signal_label(pnl_range),
        }

    # Top 50 combos: spread analysis
    top_50 = train_results[:50]
    top_spread = {}
    if top_50:
        for pname in param_names:
            vals = [r["params"][pname] for r in top_50]
            unique_vals = sorted(set(vals))
            spread = max(vals) - min(vals) if len(vals) > 1 else 0
            top_spread[pname] = {
                "unique_values": unique_vals,
                "unique_count": len(unique_vals),
                "range": spread,
                "mode": _mode(vals),
            }

    # Interpretation
    interpretation = _interpret(per_param, top_spread, param_names)

    return {
        "per_parameter": per_param,
        "top_50_spread": top_spread,
        "interpretation": interpretation,
    }


def _signal_label(pnl_range: float) -> str:
    if pnl_range >= 2.0:
        return "STRONG"
    if pnl_range >= 0.50:
        return "MODERATE"
    return "WEAK"


def _mode(values: list):
    from collections import Counter
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _interpret(per_param: dict, top_spread: dict, param_names: list) -> dict:
    strong_params = [p for p in param_names if per_param[p]["signal"] == "STRONG"]
    moderate_params = [p for p in param_names if per_param[p]["signal"] == "MODERATE"]
    weak_params = [p for p in param_names if per_param[p]["signal"] == "WEAK"]

    # Are the top 50 clustered (most params have 1-2 unique values) or scattered?
    clustered_params = []
    if top_spread:
        max_unique = max(
            (len(v.get("unique_values", [])) for v in top_spread.values()),
            default=0
        )
        for p, info in top_spread.items():
            if len(info.get("unique_values", [])) <= max(2, max_unique // 2):
                clustered_params.append(p)

    return {
        "strong_signal_params": strong_params,
        "moderate_signal_params": moderate_params,
        "weak_signal_params": weak_params,
        "top_50_clustered_params": clustered_params,
        "overall": _overall_verdict(strong_params, moderate_params, top_spread),
    }


def _overall_verdict(strong: list, moderate: list, top_spread: dict) -> str:
    if not strong and not moderate:
        return "NO SIGNAL: No parameter shows meaningful cluster differentiation. Results are likely noise."
    if strong:
        return f"SIGNAL DETECTED: {', '.join(strong)} show strong differentiation. Worth investigating these parameters specifically."
    return f"WEAK SIGNAL: {', '.join(moderate)} show moderate differentiation. Inconclusive — may be noise at this sample size."
