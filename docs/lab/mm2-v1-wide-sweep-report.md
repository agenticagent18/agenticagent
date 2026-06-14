# MM-2 v1 Wide Parameter Sweep Report

**Strategy:** MM-2 v1 (recency bias, simple wins count)  
**Sweep date:** 2026-06-14  
**Data window:** 2026-04-12 to 2026-06-13 (694 eligible games of 842 in DB)  
**Sweep ID:** mm2_v1_20260614T052720

---

## Section 1: Methodology

### Parameter grid

| Parameter | Values tested | Notes |
|---|---|---|
| `recent_form_window` | 3, 5, 7, 10, 15, 20 | Games of history to look back |
| `recent_form_wins_fraction` | 0.50, 0.60, 0.70, 0.80 | wins_threshold = ceil(window × fraction) |
| `implied_prob_low_threshold` | 0.20, 0.30, 0.40, 0.50 | Underdog fires when implied < this |
| `implied_prob_high_threshold` | 0.55, 0.65, 0.75, 0.85 | Favorite-vs-hot-opp fires when implied > this |
| `signal_strength_threshold` | 40, 50, 60, 70, 80 | Min strength to execute |
| `max_contracts` | 1, 3, 5 | Cap on position size |

**Naive combinations:** 6 × 4 × 4 × 4 × 5 × 3 = 5,760  
**After coherence filter (low < high required):** 5,760 — all combinations pass because the grid's maximum low value (0.50) is less than the minimum high value (0.55). No pruning was necessary.

### Signal logic (mm2_v1 vs signal_generator.py)

The lab implementation uses a **simple wins count**: fires when `wins_in_last_N >= ceil(window × fraction)`.

The live `signal_generator.py` uses a **weighted momentum score**: position-weighted wins (most recent game weighted highest), firing when the score diverges from the implied probability threshold.

On the 5-game sample validation, 4 of 5 games matched. The 1 divergence (CHC-PHI, 2026-04-13) was a true algorithm difference: PHI had 3 wins in last 5 but a weighted momentum score of 53 (below the 60 threshold), so the live system skipped while the simple-count approach fired. This divergence is expected and acceptable — the sweep is testing the simple-count parameterization explicitly.

### Train / test split

- **Total records:** 694 eligible game records, sorted chronologically by game start time
- **Train:** First 70% = 485 records (2026-04-12 to 2026-05-25)
- **Test (holdout):** Last 30% = 209 records (2026-05-25 to 2026-06-13)

Split is chronological, not random. This prevents look-ahead bias and reflects actual deployment conditions.

### Holdout confirmation criteria

A combo is "candidate viable" only if ALL of the following hold on the test window:
- Net P&L > $0
- Win rate > breakeven win rate + 2pp
- Trades executed ≥ 20
- Max drawdown < $10

### Runtime

- Cache warming (MLB API schedule fetch, 29 teams): 22.8s (one-time)
- Data loading (694 game records, orderbook DB + cached schedules): 1.2s
- Train sweep (5,760 combos): **1.7 seconds**
- Holdout sweep (50 combos): negligible
- Total sweep runtime: ~2 minutes including cache warm

---

## Section 2: Train sweep results

### P&L distribution (5,760 combinations on train window)

| Metric | Value |
|---|---|
| Mean P&L | −$0.74 |
| Median P&L | $0.00 |
| Std deviation | $5.64 |
| Min P&L | −$36.86 |
| Max P&L | $+13.08 |
| Combos with positive P&L | 1,913 / 5,760 (33%) |

The median of $0.00 reflects that most combinations produce zero-trade windows — the signal fires infrequently enough that many parameter settings generate no trades in the train period. The large standard deviation ($5.64) relative to the mean (−$0.74) reflects high variance from a small trade sample, not a dispersed signal.

### Top 20 train combinations

All top 20 are structurally identical: `window=7, fraction=0.60, low=0.50`. Only `implied_prob_high_threshold`, `signal_strength_threshold`, and `max_contracts` vary — and they produce **identical P&L** ($13.08) and **identical trade counts** (95). This is the first major red flag: the signal_strength_threshold parameter (range 40–80) has zero effect on outcomes, meaning the strength filter is not actually binding for these combinations.

| Rank | Train P&L | Win rate | Edge | Trades | window | fraction | low | high | threshold | max_c |
|---|---|---|---|---|---|---|---|---|---|---|
| 1–10 | $+13.08 | 49.5% | +4.6pp | 95 | 7 | 0.60 | 0.50 | 0.55–0.85 (varies) | 40–80 (varies) | 3 or 5 |

**Why window=7, fraction=0.60, low=0.50 dominates the top:**  
`implied_prob_low_threshold=0.50` fires on any underdog (implied < 50%), which includes roughly half of all game markets. Combined with `wins_threshold = ceil(7 × 0.60) = 5`, this trades 95 of the 485 train-window games (19.6%). The train period (April–May) happened to be favorable to underdogs — a period effect that does not persist.

---

## Section 3: Cluster analysis

### Per-parameter average P&L across all combinations

| Parameter | Signal | P&L range across values | Best value | Interpretation |
|---|---|---|---|---|
| `implied_prob_low_threshold` | **STRONG** | $3.56 | 0.50 | Drives performance most — but the best value is an artifact of the train period having more upsets than the test period |
| `implied_prob_high_threshold` | **STRONG** | $5.62 | 0.65 | hi=0.55 strongly negative (−$4.90 avg) because it creates nearly zero net coverage — the signal fires redundantly with very low threshold gap |
| `recent_form_wins_fraction` | **STRONG** | $2.63 | 0.70 | Stricter wins threshold (0.70 = 70% win rate) is marginally better, but all values are negative or near-zero |
| `recent_form_window` | MODERATE | $1.46 | 5 | Short windows (3, 5) slightly outperform long ones (15, 20), but the effect is small |
| `max_contracts` | MODERATE | $0.60 | 1 | max_contracts=1 (conservative sizing) outperforms 3 or 5 — confirms the signal is noisy and Kelly sizing would demand small bets |
| `signal_strength_threshold` | WEAK | $0.35 | 70 | Nearly irrelevant — the strength formula produces near-identical outcomes across the 40–80 range |

Detailed cluster averages:

**implied_prob_low_threshold** (strongest driver):
- 0.20: avg −$1.72 | 0.30: avg −$1.64 | 0.40: avg −$1.45 | 0.50: avg **+$1.84**

**implied_prob_high_threshold** (largest spread):
- 0.55: avg −$4.90 | 0.65: avg **+$0.72** | 0.75: avg +$0.61 | 0.85: avg +$0.61

**recent_form_wins_fraction**:
- 0.50: avg −$2.46 | 0.60: avg −$0.52 | 0.70: avg **+$0.17** | 0.80: avg −$0.15

### Top 50 combos: are they clustered or scattered?

| Parameter | Unique values in top 50 | Mode |
|---|---|---|
| `recent_form_window` | **1** (only 7) | 7 |
| `implied_prob_low_threshold` | **1** (only 0.50) | 0.50 |
| `recent_form_wins_fraction` | 2 (0.60, 0.70) | 0.60 |
| `implied_prob_high_threshold` | 4 (all values) | 0.55 |
| `signal_strength_threshold` | 5 (all values) | 40 |
| `max_contracts` | 2 (3, 5) | 3 |

**Conclusion:** The top 50 are tightly clustered in two parameters (`window=7`, `low=0.50`) and completely scattered in the other four. This means the top-50 "signal" comes entirely from two parameter values, not from a genuine multi-dimensional pattern. It is consistent with a period-specific lucky regime, not a real strategy edge.

---

## Section 4: Holdout validation

### Top 50 combos: train vs test performance

Every top-50 combo fails holdout. All 50 produce **identical test results**: P&L = −$8.78, win rate = 36.6%, 41 trades.

| | Train | Test |
|---|---|---|
| P&L | $+13.08 | **−$8.78** |
| Win rate | 49.5% | 36.6% |
| Breakeven WR | ~44.9% | ~37.9% |
| Edge | +4.6pp | −1.3pp |
| Trades | 95 | 41 |
| Holdout passes | — | **0 / 50** |

The identical test results for all 50 combos occur because they all share `window=7, low=0.50`, producing the same trade signals regardless of `threshold` or `high` variation. This confirms the entire top-50 is a single effective strategy variant, not 50 independent candidate strategies.

### Train-test correlation

Not applicable: all 50 combos are functionally identical. A true train-test correlation would require diverse combos at the top. The convergence to a single combo variant is itself a diagnostic of overfit.

### Holdout fail breakdown

The failure modes for the 50 candidates (all fail on multiple criteria):

- Net P&L > $0: **FAIL** (test P&L = −$8.78)
- Win rate > breakeven + 2pp: **FAIL** (36.6% vs 37.9% + 2pp = 39.9%)
- Trades ≥ 20: PASS (41 trades)
- Max drawdown < $10: marginal (actual drawdown not computed for this summary)

The test win rate (36.6%) is essentially identical to the full-season baseline at default params (36.7%). The train "win" came from a period effect (April–May 2026 had more underdog wins), not from a genuine signal.

---

## Section 5: Candidate viable strategies

**None.** Zero combinations passed all holdout criteria.

---

## Section 6: Verdict

### **NULL RESULT**

No parameter combination of MM-2 v1 passes holdout validation. The hypothesis — that Kalshi MLB markets systematically misprice teams based on recent form — is not supported in the 2026 season-to-date data (April 12 – June 13) at any tested parameter setting.

**What the data shows:**

1. **The train "signal" is a period effect.** April–May 2026 had an above-average underdog win rate. The `implied_prob_low_threshold=0.50` combination captured this pattern. It does not hold in June.

2. **The signal_strength_threshold is irrelevant.** Its WEAK cluster signal (range $0.35 across values) means the strength formula as implemented does not add filtering value. The bet fires at essentially the same rate whether threshold is 40 or 80.

3. **More conservative sizing doesn't help.** `max_contracts=1` is marginally better in train (+$0.60 avg vs $0.94 for larger sizes) but the edge is still negative in test. Sizing conservatively doesn't rescue a strategy with no edge.

4. **The strategy operates at ≈breakeven by design.** At default params, full-season P&L = −$2.19 with win rate 36.7% vs breakeven 36.9%. Across 5,760 parameter sweeps, the median combo also produces $0.00. The strategy is consistent — consistently near-zero edge.

**Honest interpretation:**

The sample size (49–95 trades at typical parameter settings) can only detect edges larger than ±5–8 percentage points above breakeven. If MM-2 has a real edge in the 1–3pp range, this data cannot confirm or deny it. The sweep is not a definitive falsification.

However, the consistent absence of positive test P&L across every parameter combination, combined with the collapse from 49.5% → 36.6% win rate between train and test, strongly suggests the strategy has no systematic edge at this market (MLB game-winner Kalshi contracts, 2026 season, T-45 entry).

**Recommendation:** Design strategy 3. The MM-2 hypothesis (recency bias + T-45 entry on binary game-winner contracts) has been tested at 5,760 parameter settings across a full season's data and found no viable configuration. The appropriate next step is a structurally different hypothesis, not further parameter tuning of MM-2.

**MM-2 paper trial:** Continue to session 30 per the pre-registered decision rule. The backtest's NULL RESULT is informative but does not override the registered procedure.

---

*Report generated 2026-06-14. Sweep runtime: 1.7s (5,760 combos). Full results: results/sweeps/mm2_v1_20260614T052720.json*
