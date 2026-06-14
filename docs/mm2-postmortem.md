# MM-2 Phase 1 Postmortem

**Killed:** 2026-06-15, after 5 sessions of live paper trading and a comprehensive backtest.

---

## Summary

- **5 live paper sessions:** 7 trades, +$3.35 net P&L on $50 starting capital
- **Lab sweep:** 5,760 parameter combinations on 694-game historical dataset — NULL RESULT (no combination passed holdout validation)
- **Investigation:** only 1 of 7 live trades represented a valid test of the pre-game-mispricing hypothesis (Jun 12 PHI trade); 6 traded against in-game prices due to a bug in `get_kalshi_price_from_db()`

---

## Hypothesis (What We Tested)

The Kalshi MLB game-winner market overreacts to old form and underweights recent results. When market-implied probability and recent-form streak disagree, recent form is more predictive. A pre-game directional position betting on the team the market undervalues captures this mispricing.

Operationally: if a team is implied <40% but won 3 of its last 5 games, buy YES on that team at T-45 minutes before first pitch.

---

## What the Lab Found

**Sweep:** 5,760 parameter combinations across 6 dimensions (form window, form threshold, implied probability bands, signal strength threshold, position size). 694 eligible games from April 12 – June 13, 2026. Train: 485 games (Apr 12 – May 25). Test: 209 games (May 25 – Jun 13).

**Train results:**
- Best train P&L: +$13.08 (at `window=7, low_threshold=0.50` — any underdog fires)
- Mean P&L across all 5,760 combos: −$0.74
- Combos with positive P&L: 1,913 of 5,760 (33%)
- Top 50 combos were structurally identical: all shared `window=7, low=0.50`, producing 95 of 485 train trades

**Cluster analysis:**
- `implied_prob_low_threshold` was the strongest driver — but its best value (0.50, any underdog) was a period effect, not a signal
- `signal_strength_threshold` (range 40–80) had WEAK cluster signal ($0.35 spread) — the strength formula was not effectively filtering in this data
- `implied_prob_high_threshold=0.55` was strongly negative (creates near-zero coverage gap)

**Holdout results (top 50 combos on Jun test window):**
- Every top-50 combo: P&L = −$8.78, win rate = 36.6%, 41 trades
- All 50 are functionally identical — they all share `window=7, low=0.50`
- Holdout pass criteria: P&L > $0, edge > breakeven + 2pp, trades ≥ 20, drawdown < $10
- **Holdout candidates: 0 / 50**

The train "win" came from April–May 2026 having an above-average underdog win rate. That period effect did not persist into June.

---

## What the Live Trial Actually Tested

The live system runs `signal_generator.py` at 20:30 UTC (4:30 PM ET). Day games start at 17:05–18:15 UTC (1:05–2:15 PM ET). The price query — `SELECT ... ORDER BY id DESC LIMIT 1` with no time constraint — returns the most recent orderbook record regardless of when it was recorded.

| Session | Date | Outcome | Price issue |
|---|---|---|---|
| 1 | Jun 7 | DET +90.5¢, STL +20¢, ATL +43¢ | **In-game prices.** Games had been underway 2–3 hours. T-45 prices were 58.5%, 47.5%, 56.5% — neither algorithm would fire. |
| 2 | Jun 8 | PHI +61.5¢ | **Stale/wrong price.** Signal log showed PHI implied 37%, execution at 61.5¢. At T-45, both algorithms would buy TOR (38.5¢ underdog), not PHI. |
| 3 | Jun 10 | TB +1¢ | **In-game price near settlement.** TB was losing when cron fired. |
| 4 | Jun 11 | STL +0.5¢ | **In-game price near settlement.** STL was losing when cron fired. |
| 5 | Jun 12 | PHI ✓, TB ✗, DET (n/a) | PHI trade aligned with both algorithms. TB direction conflicted with lab due to different price snapshots. DET not in lab backtest. |

**Of 7 live trades, only 1 (Jun 12 PHI) qualifies as pre-game evidence of the MM-2 hypothesis.** The +$3.35 net P&L is not interpretable as confirmation or denial of the strategy.

---

## Root Causes

**1. The hypothesis was wrong, or the signal is period-specific.**

Lab train data (Apr–May) showed a positive signal that collapsed entirely in the June holdout. The underlying cause is either: (a) April–May 2026 had an unusually high underdog win rate (period effect, not a market inefficiency), or (b) the sample size (49–95 trades at typical settings) is too small to detect an edge in the 1–3pp range. Across 5,760 parameter combinations, the median combo produced $0.00. The strategy is near-zero edge consistently.

**2. The live executor had a price-query bug that contaminated all but one trade.**

`get_kalshi_price_from_db()` used `ORDER BY id DESC LIMIT 1` — no time constraint. For day games with 4:30 PM ET signal cron timing, this returned in-game or near-settlement prices. The bot reported successful executions, but the trades weren't testing the pre-game hypothesis. This is the same monitoring-disease pattern as the ghost crisis (posts appeared to post, but weren't visible) and the solver bug (answers appeared to submit, but the outcome wasn't checked).

---

## What This Falsifies

MM-2 v1 hypothesis is dead at any of 5,760 parameter settings on the April–June 2026 MLB Kalshi orderbook dataset. The specific form of the hypothesis — binary game-winner markets systematically misprice teams based on simple recent-form streaks — is not supported in this data.

Future MM-style strategies for Kalshi MLB markets should not rely on:
- Simple recent-win-count (unweighted) as the form signal
- T-45 directional single-leg positions on game-winner markets
- The April–May 2026 underdog win rate as a baseline

---

## What This Doesn't Falsify

- The orderbook dataset itself remains valid and valuable
- Other hypotheses on Kalshi MLB game-winner pricing remain open
- Weighted momentum scoring (live system's approach) is closer to the hypothesis than the simple wins count, and was not independently tested with proper price data
- The strategy lab and sweep methodology is validated and ready for strategy 3

---

## Lessons

**1. Pre-register decision rules before data accumulates.** The decision rule was pre-registered at session 2. The lab sweep result triggered the kill without negotiating with accumulated evidence. This worked as designed.

**2. Build the backtest before the live trial.** The strategy lab was built after MM-2 launched live. If the 5,760-combo sweep had run in April, MM-2 would never have launched — the NULL RESULT was visible in the historical data. Backtest-first is now the standing policy.

**3. Verify intended outcomes, not just API success.** The live trial illustrates the doctrine codified in the outcome verification policy (see `outcome-verification-doctrine.md`). The executor ran, logged success, and produced P&L — but the intended outcome (pre-game entry at T-45 prices) was not verified. The verification gap made the trial invalid as evidence.

---

## Status

**KILLED 2026-06-15.** Crontab disabled (four lines commented with KILLED prefix). Code preserved in `~/.openclaw/workspace/mm2/` for reference. Strategy lab preserved in `~/.openclaw/workspace/strategy_lab/` with full sweep results.

Final paper P&L: **+$3.35** — invalid as evidence of strategy edge; 6 of 7 trades executed against contaminated prices.
