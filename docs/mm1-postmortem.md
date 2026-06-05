# MM-1 Postmortem: Symmetric Market Making on Kalshi MLB Markets

**Period:** April 17 – May 21, 2026  
**Sessions:** 22 total (12 active, 10 zero-fill from API outages)  
**Result:** -$107.67 cumulative P&L, account negative at session close

---

## What MM-1 Was

A classical symmetric market maker on Kalshi MLB game winner markets. The strategy:

1. At 6pm ET, open a session against tonight's MLB slate
2. Post bid and ask quotes around the midpoint of each YES/NO market
3. Collect the spread from uninformed flow (passive fills)
4. Flatten inventory at session end

No directional view. Profit from being the price discovery service, not from predicting outcomes.

## Session Performance

| Session | Date | Fills | Adverse% | P&L | Cash After |
|---------|------|-------|----------|-----|------------|
| #4 | 2026-05-03 | 8 | 62% | -$2.18 | $97.82 |
| #12 | 2026-05-11 | 15 | 46% | -$7.96 | $89.86 |
| #13 | 2026-05-12 | 14 | 36% | -$6.45 | $83.41 |
| #14 | 2026-05-13 | 22 | 44% | -$13.17 | $70.24 |
| #15 | 2026-05-14 | 25 | 44% | -$11.59 | $58.65 |
| #16 | 2026-05-15 | 18 | 39% | -$8.20 | $50.45 |
| #17 | 2026-05-16 | 15 | 60% | -$8.46 | $41.99 |
| #18 | 2026-05-17 | 12 | 33% | -$6.56 | $35.43 |
| #19 | 2026-05-18 | 18 | 18% | -$7.94 | $27.49 |
| #20 | 2026-05-19 | 27 | 43% | -$11.94 | $15.55 |
| #21 | 2026-05-20 | 22 | 24% | -$11.30 | $4.25 |
| #22 | 2026-05-21 | 26 | 40% | -$11.92 | **-$7.67** |

**Mean adverse selection: 41%** (range 18–62%)

Healthy market making tolerates ~30%. Above 35% is structural.

## Root Cause

**The fundamental assumption was wrong.** Market making works when prices are mean-reverting. MLB game winner prices are trending:

- At first pitch, the market opens near 50/50 for balanced matchups
- As innings progress, the winning team's probability moves monotonically upward
- A market maker quoting symmetrically is short gamma: every price move expands losses
- Informed traders (who watch live scores) fill against stale quotes

This is adverse selection by construction. Every fill at a "stale" price is adverse because the market always knows more than the bot does about the current score state.

No parameter tuning fixes a structural problem. Tightening the halt threshold, reducing quote size, adjusting inventory limits — these are symptoms, not causes.

## The Broken Metric That Misled Four Analysis Cycles

`post_session_analysis.py` reported **0% adverse selection for all 22 sessions**.

The bug: the script read `adverse_selected` from the JSONL event log. Fill events are logged at fill time. The adverse scoring function runs *later* — after `ADVERSE_SELECTION_WINDOW_SECONDS` elapses — and writes only to the SQLite database, not the JSONL.

Result: four post-session AI analysis cycles (sessions 18–21) ran on corrupted data and recommended parameter adjustments. The AI was treating a structural design failure as a tuning opportunity.

The corrected adverse rates (from the DB) ranged from 18% to 62%, with a mean of 41%.

## What Was Built (and Saved)

The infrastructure shipped during MM-1 is real and reusable:

- **Retry queue**: ghost post detection + 24h expiry window + dedup logic
- **Health sentinel**: 4-layer monitoring, 30-min heartbeat, escalation
- **Quality monitor**: 267 quality checks accumulated
- **Post-session analysis framework**: fixed to query DB, now authoritative

None of this was wasted. MM-2 inherits the infrastructure.

## What MM-2 Does Differently

MM-2 is a directional trader, not a market maker:

- Take one pre-game position based on analysis, hold through resolution
- No mid-game quoting (eliminates adverse selection entirely)
- Phase 1 hypothesis: Kalshi prices overweight recent team form vs season record
- Signal: if market implies >65% but team is on a losing streak, buy the underdog

See `mm2-design.md` for the full design.
