# mm-2 phase 1 backtest specification
registered 2026-06-14, before implementation

## hypothesis under test
the kalshi mlb game-winner market overreacts to old form and underweights recent results. when market-implied probability and recent-form streak disagree, recent form is more predictive.

## test conditions
- scope: every MLB game in the orderbook DB with sufficient data (defined below)
- entry: simulated at T-minus-45 minutes from game start, using the most recent yes_bid/yes_ask snapshot at that timestamp
- signal logic: identical to mm2/signal_generator.py
  - BUY_YES on a team if: implied probability < 40% AND team has 3+ wins in last 5 games (underdog momentum)
  - BUY_YES on a team if: implied probability > 65% AND OPPONENT has 3+ wins in last 5 games (market favorite vs hot opponent — market underweighting opponent's form)
  - signal strength score: implemented in signal_generator.py — use exact same scoring
  - threshold for action: strength >= 60 (identical to live)
- position sizing: 1-3 contracts based on strength, identical to live position_executor.py
- daily loss cap: $5/day simulated. once a day's losses reach -$5, no more positions that day
- settlement: 100¢ if the team won, 0¢ if lost
- P&L: (settlement - entry_price) * contracts, in dollars

## data requirements per game
- game start time (MLB API or orderbook DB)
- both teams' last 5 game results as of game date
- kalshi market ticker for the game
- yes_bid/yes_ask snapshot from orderbook at T-minus-45 (closest snapshot within 60 seconds tolerance)
- game outcome (winner)
- settlement price (if available in DB, otherwise inferred 0/100 from outcome)

## exclusion criteria (game excluded from backtest)
- recent form data unavailable for either team (early-season games)
- no orderbook snapshot within 60 seconds of T-minus-45
- ambiguous or missing settlement
- game suspended/postponed/rescheduled

## metrics to report (must match docs/mm2-decision-rule.md)
- total games eligible / total games traded / signals skipped
- net P&L ($ and % of $50)
- trade count
- win rate (vs breakeven implied by average entry price)
- average return per trade
- max drawdown
- $5 daily-stop hits (count of days where cap was hit)
- top-2-trade share of gross profit
- daily P&L distribution

## decision interpretation
this is informational only. it does NOT trigger any branch of the live trial decision rule. results inform:
- if positive edge confirmed: high confidence to continue Phase 1, EXTEND branch at session 30 more likely
- if no edge: provides falsification evidence for Phase 1 hypothesis, ITERATE or KILL branches more likely
- if backtest contradicts live results: investigate causes (timing pollution, data differences, sample size)
