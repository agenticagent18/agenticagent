# MM-2 Design Document

**Status:** Design only — implementation in a dedicated future session  
**Created:** 2026-05-21  
**Prerequisite reading:** PAUSED_STATE.md, MM1_ANALYSIS_CORRECTED.md

---

## 1. Lessons from MM-1

### What MM-1 Was

Classical symmetric market making: post a bid-ask spread around the midpoint of the
Kalshi MLB game winner market, collect the spread from uninformed flow, flatten inventory
daily. No directional view. Profit from being the price discovery service, not from
predicting outcomes.

### Why It Failed

**The fundamental assumption was wrong.** Market making works when prices are mean-reverting
(oscillate around fair value). MLB game winner prices are trending:

- At first pitch, the market is near 50/50 (for balanced matchups).
- As innings progress, the winning team's probability moves monotonically upward.
- A market maker who quotes symmetrically is short gamma: every price move expands losses.
- Informed traders (who watch live scores) fill against stale quotes. This is adverse
  selection by construction, not by bad luck.

The corrected adverse selection rate from the fills database: **mean 41% across 12 active
sessions** (range 18–62%). Healthy market making tolerates ~30%. Above 35% is structural.

### Capital Summary

| Metric | Value |
|--------|-------|
| Starting paper capital | $100.00 |
| Final paper cash | -$7.67 |
| Cumulative P&L | -$107.67 |
| Active trading sessions | 12 |
| Sessions with 0 fills | 10 (API outages / off days) |
| Avg loss per active session | -$8.97 |
| Worst single session | -$13.17 (May 13) |

The account went below zero in session #22 (May 21), the final session before pause.

### What the Post-Deployment Fixes Achieved (May 17)

- Retry queue, ghost detection infrastructure, AI augmentation layers: **shipped and working**
- MM-1 per-session losses: **unchanged** (still -$8–12/session)
- Root cause (trending market structure): **unaffected by parameter changes**

The infrastructure improvements are real and reusable for MM-2. The strategy was the problem.

---

## 2. MM-2 Strategic Positioning

### Core Shift

**From:** symmetric market maker (no view, collect spread)  
**To:** directional trader (take a position based on pre-game analysis, hold through resolution)

This inverts the adverse selection problem. Instead of being the counterparty to informed
traders, MM-2 tries to be the informed trader.

### Phase 1: Pre-Game Positioning (lower risk, smaller edge)

- Enter positions 30–60 minutes before first pitch, when markets are open but information
  advantage is minimal.
- Use public data (team records, pitcher matchups, Vegas implied odds) to assess whether
  Kalshi's market price is mispriced relative to a simple model.
- Hold position until 30 minutes after expected game end, then close at market.
- No mid-game intervention. Eliminates adverse selection from live-game information leakage.

### Phase 2: In-Game Adjustment (higher risk, larger edge)

- Unlock only after Phase 1 demonstrates positive expectancy over 30 sessions.
- Use live score state to make one mid-game position adjustment per game.
- Limited to games where we entered pre-game (no cold entries mid-game).

---

## 3. Edge Thesis

Where could a small bot ($50 paper capital, 1–3 contracts per game) plausibly have edge
against Kalshi MLB winner markets?

**Hypothesis 1: Recency bias in public pricing** *(recommended for Phase 1)*  
Markets overweight recent team performance (last 3–5 games) relative to season record.
A team on a 3-game losing streak but with a strong 30-game record may be mispriced.
Test: compute "implied probability vs season win rate" delta; bet the mean-reversion.

**Hypothesis 2: Pitcher matchup underutilization**  
Retail money prices games based on team brand recognition. Starting pitcher quality
(ERA, WHIP, recent starts) may be underweighted in the Kalshi price vs sharper markets
(FanDuel, DraftKings). Test: compare Kalshi implied probability vs Vegas-line-derived
probability; fade large divergences.

**Hypothesis 3: Late market movement signals sharp activity**  
Price movements in the 30 minutes before first pitch often reflect sharp bettor positioning.
Following late-breaking consensus direction may capture information from better-informed
participants. Test: enter in same direction as 10-minute price move in final window.

**Phase 1 recommendation: Hypothesis 1** (recency bias). It requires only public season
records (easily available from MLB API), has a testable signal (season win% vs implied
probability), and is not contingent on market microstructure access. It also doesn't
require reading real-time price movements, which simplifies implementation.

---

## 4. Architecture Sketch

```
[5:55pm ET — pre-session analysis]
  DeepSeek reads: MLB schedule for today, season records, pitcher matchup,
  Vegas implied probabilities (scraped from public sources)
  → Generates per-game recommendation: BUY_YES / BUY_NO / SKIP
  → Includes: confidence (high/medium/low), size (1–3 contracts), reasoning
  → Writes to mm2/pre_game_recommendations.json

[6:00pm–7:30pm ET — position entry window]
  Mechanical wrapper reads recommendations
  For each HIGH/MEDIUM confidence game: place directional order 30–60min pre-pitch
  No market making — single entry, no requoting
  Writes to mm2/open_positions.json

[12:00am ET — position close sweep]
  For each open position from tonight: close at market price
  This is 30min after the latest possible MLB game end (typically 11:30pm ET)
  Writes P&L to mm2/session_log.jsonl

[2:00am ET — post-session analysis]
  Existing post_session_analysis.py adapted for directional format
  Reviews: which recommendations were correct, calibration of confidence scores
  Detects: if one edge hypothesis is working, flag for parameter refinement
  Detects: if all three hypotheses are flat, recommend Phase 1 stop
```

### Key Design Decisions vs MM-1

| Decision | MM-1 | MM-2 |
|----------|------|------|
| Entry logic | Quote both sides, fill passively | Single directional entry, active |
| Fill timing | During session (continuous) | Pre-game only (30–60min window) |
| Hold duration | Until inventory flattened or session end | Until 30min post-game |
| Close logic | Cancel all orders at drawdown limit | Scheduled close sweep |
| Adverse selection | Structural (quoting against informed) | Minimized (no mid-game quotes) |
| AI role | Post-hoc analysis of losses | Pre-game signal generation |

---

## 5. Risk Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Starting paper capital | **$50** (reset) | Clean start; not a continuation of MM-1 wreckage |
| Max position size | 3 contracts per game | Limits single-game exposure |
| Max simultaneous positions | 3 games per night | Diversification; no more than $9–15 at risk nightly at 3c contract |
| Max daily loss | $5 (10% of capital) | Hard stop — triggers Phase 1 review |
| Sessions per week | 5 (skip weekends with thin slates) | Avoids low-liquidity games |
| Phase 1 duration | 30 sessions (~6 weeks) | Statistical minimum for edge detection |

Note: Kalshi MLB contracts typically trade at 30–70c, meaning 1 contract = $0.30–$0.70 cost.
3 contracts per game × 3 games = max $6.30 deployed per session at 70c average price.

---

## 6. Success Criteria

### Phase 1 Success
- Positive cumulative paper P&L after 30 sessions
- Win rate on HIGH confidence recommendations: >55% (better than coin flip)
- Win rate on MEDIUM confidence recommendations: >50%
- No single recommendation type generating >60% losses (would indicate that hypothesis
  is directionally backwards)

### Phase 1 Failure (stop and redesign)
- Cumulative paper loss exceeds $15 (30% of starting capital) at any point
- Win rate < 45% over first 20 sessions with no improvement trend
- DeepSeek recommendations show no calibration (confidence doesn't correlate with win rate)

### Phase 2 Unlock
- Phase 1 completes with positive expectancy
- Confidence calibration: HIGH confidence games win >60%, LOW confidence games win ~50%
- Decision made jointly with operator after Phase 1 review

### Real-Money Consideration
- Not before: 60 Phase 1 sessions (3 months) of positive paper P&L
- Not without: statistical significance check (binomial test, p < 0.05)
- Not until: MM-2 infrastructure proven stable for 30+ sessions without operational errors

---

## 7. Open Questions (for future sessions)

**Q1: Which edge hypothesis do we test first?**  
Recommendation: Hypothesis 1 (recency bias). But Hypothesis 2 (pitcher matchup) may be
stronger if we can reliably scrape Vegas lines for comparison. Decision needed before
implementation.

**Q2: Do we train a real ML model on the 30M-event Kalshi orderbook history?**  
The 6.5GB SQLite database contains 186M+ events. Analysis pipeline is broken (exec timeout).
Fix the reader first (chunked queries or SQLite WAL streaming), then decide if the data
has signal worth the analysis cost. DeepSeek + structured public data is the faster path.

**Q3: Statistical significance threshold.**  
With 3 contracts per game, 3 games per night, 5 nights/week, edge of 5 percentage points
above chance: need ~100 bets for 80% power at p=0.05. Phase 1's 30 sessions × 3 games =
~90 bets. Borderline. Consider whether to extend Phase 1 to 40 sessions for cleaner signal.

**Q4: At what point do we consider real-money trading?**  
Paper trading removes several real constraints: latency (API response times), liquidity
(can we actually fill at paper prices?), slippage (queue position). Before real money:
run a 10-session "shadow mode" where we place real orders but at prices 5c worse than
paper orders, to empirically measure execution quality.

**Q5: What's the correct DeepSeek prompt for pre-game analysis?**  
The Level 1 veto prompt was written for market-making (identify adverse markets). MM-2
needs a different prompt: generate a directional recommendation with confidence calibration.
Needs careful design to avoid the AI confidently predicting every game — calibration is
the hard part. Test prompt design separately before wiring into cron.
