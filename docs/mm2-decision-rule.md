# mm-2 phase 1 — pre-registered decision rule
registered 2026-06-12, after seeing results through session 2 (june 8,
+$3.35) and before reading any later results. branches below are frozen at
this commit; changelog appends only.

## definitions
- session: a calendar day with >=1 qualifying MLB market and >=1 paper
  order placed. non-trading days do not count toward 30.
- trial ends at session 30 or on a kill trigger, whichever comes first.
- no changes to entry logic, sizing, or stops during the trial. bug fixes
  allowed; log them in the changelog. if a bug materially affected 3+
  sessions, restart the session count from the fix date.

## metrics at evaluation
net p&l ($ and % of 50), trade count, win rate, average entry price and
implied breakeven win rate, average return per trade, max drawdown, count
of $5 daily-stop hits, share of gross profit from top 2 trades.

## branches
KILL — any of: cumulative p&l <= -$15 at any point; daily stop hit on 5+
sessions; at session 30, p&l < $0 with win rate below breakeven.
action: write mm2-postmortem.md in the mm1 style; archive the strategy.
ITERATE — at session 30: -$15 < p&l < +$5, OR p&l positive but top 2
trades account for >50% of gross profit.
action: hypothesis neither supported nor falsified. next step is the
minimal orderbook backtest. no redesign, no extension.
EXTEND (paper only) — at session 30: p&l >= +$5 AND >=40 trades AND win
rate >= breakeven + 3pp AND top-2-trade share <= 50% of gross.
action: extend paper trial to 90 sessions, identical parameters; run the
minimal backtest in parallel.

## hard constraint
no branch of this trial authorizes live trading. LIVE_TRADING=False is out
of scope for phase 1 regardless of results. a live discussion requires all
of: 90+ paper sessions with positive edge, backtest concordance on at
least one full season of orderbook data, and a separate explicit decision
session.

## statistical honesty
at 60-150 trades this trial can only detect large edges. EXTEND means
"worth more investigation," not "edge established."

## changelog
(appends only)
