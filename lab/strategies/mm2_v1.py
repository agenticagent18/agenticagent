"""
MM-2 v1: Recency bias strategy, parameterized for sweep.

Hypothesis: Kalshi markets overweight recent team form. When a team's
implied probability diverges from its recent win rate, bet on reversion.

Signal logic follows mm2_phase1_backtest.py canonical implementation.

DEFAULT_PARAMS produce decisions consistent with signal_generator.py under
normal conditions. Key algorithmic difference: signal_generator.py uses a
weighted momentum score (position-weighted wins), while this implementation
uses a simple wins count (wins >= ceil(window * fraction)). The two agree
in most cases but diverge when wins are concentrated at the tail of the window.
This discrepancy is documented in the validation output.
"""

from __future__ import annotations

import math
from typing import Optional

from engine.strategy_base import GameContext, Signal, StrategyBase


class MM2V1(StrategyBase):
    STRATEGY_ID = "mm2_v1"

    DEFAULT_PARAMS = {
        "recent_form_window": 5,
        "recent_form_wins_fraction": 0.60,   # wins_threshold = ceil(window * fraction)
        "implied_prob_low_threshold": 0.40,
        "implied_prob_high_threshold": 0.65,
        "signal_strength_threshold": 60,
        "max_contracts": 3,
    }

    def generate_signal(self, game_context: GameContext) -> Optional[Signal]:
        window = self.params["recent_form_window"]
        fraction = self.params["recent_form_wins_fraction"]
        low = self.params["implied_prob_low_threshold"] * 100   # convert to %
        high = self.params["implied_prob_high_threshold"] * 100
        str_thresh = self.params["signal_strength_threshold"]

        wins_threshold = math.ceil(window * fraction)

        hist_a = game_context.wins_history_a
        hist_b = game_context.wins_history_b

        # Need at least wins_threshold games available for each team
        min_needed = max(3, wins_threshold)
        if len(hist_a) < min_needed or len(hist_b) < min_needed:
            return None

        wins_a = sum(hist_a[:window])
        wins_b = sum(hist_b[:window])

        implied_a = game_context.mid_a * 100
        implied_b = 100.0 - implied_a

        # Evaluate signal for both directions; pick strongest
        sig_a = self._compute(implied_a, wins_a, wins_b, low, high, wins_threshold)
        sig_b = self._compute(implied_b, wins_b, wins_a, low, high, wins_threshold)

        if sig_a and sig_b:
            use_a = sig_a[1] >= sig_b[1]
        elif sig_a:
            use_a = True
        elif sig_b:
            use_a = False
        else:
            return None

        sig_type, strength = sig_a if use_a else sig_b
        if strength < str_thresh:
            return None

        contracts = self.size_position_from_strength(strength)
        if use_a:
            buy_team = game_context.team_a
            mkt = game_context.mkt_a
            wins_used = wins_a
        else:
            buy_team = game_context.team_b
            mkt = game_context.mkt_b
            wins_used = wins_b

        entry_pct = game_context.mid_a * 100 if use_a else (100.0 - game_context.mid_a * 100)
        return Signal(
            market_ticker=mkt,
            side="BUY_YES",
            strength=strength,
            contracts=contracts,
            reasoning=f"{sig_type}: implied={entry_pct:.1f}%, wins={wins_used}/{window}",
            signal_type=sig_type,
            buy_team=buy_team,
        )

    def _compute(self, implied_pct, team_wins, opp_wins, low, high, wins_threshold):
        """Returns (signal_type, strength) or None. Caller tracks direction."""
        if implied_pct < low and team_wins >= wins_threshold:
            strength = team_wins * 20 + (low - implied_pct)
            return ('underdog_momentum', round(strength, 1))
        if implied_pct > high and opp_wins >= wins_threshold:
            strength = opp_wins * 20 + (implied_pct - high)
            return ('favorite_vs_hot_opp', round(strength, 1))
        return None

    def size_position(self, signal: Signal, available_cash: float = 50.0) -> int:
        return self.size_position_from_strength(signal.strength)

    def size_position_from_strength(self, strength: float) -> int:
        max_c = self.params.get("max_contracts", 3)
        if strength >= 100:
            return min(3, max_c)
        if strength >= 80:
            return min(2, max_c)
        return min(1, max_c)

    @classmethod
    def validate_vs_signal_generator(cls, records: list, n: int = 5) -> None:
        """Run default-params signals on first n records and compare logic approaches."""
        strat_simple = cls({})
        print("\n=== MM2V1 vs signal_generator.py validation (5 games) ===")
        print("  mm2_v1 (simple wins count) vs signal_generator (weighted momentum)")
        print(f"  DEFAULT: window=5, fraction=0.60, wins_threshold=3, low=40, high=65\n")

        for ctx in records[:n]:
            wins_a = sum(ctx.wins_history_a[:5])
            wins_b = sum(ctx.wins_history_b[:5])
            implied_a = ctx.mid_a * 100
            implied_b = 100 - implied_a

            # Weighted momentum (signal_generator.py logic)
            def weighted_momentum(history, window=5):
                games = history[:window]
                weights = list(range(len(games), 0, -1))
                ww = sum(w for b, w in zip(games, weights) if b)
                tw = sum(weights)
                return int(ww / tw * 100) if tw else 0

            mom_a = weighted_momentum(ctx.wins_history_a)
            mom_b = weighted_momentum(ctx.wins_history_b)

            # signal_generator.py decision (simulated for historical data)
            sg_decision = "SKIP"
            sg_team = None
            if implied_a > 65 and mom_a < 40:
                sg_decision = "BUY_YES"; sg_team = ctx.team_b
            elif implied_b > 65 and mom_b < 40:
                sg_decision = "BUY_YES"; sg_team = ctx.team_a
            elif implied_a < 40 and mom_a > 60:
                sg_decision = "BUY_YES"; sg_team = ctx.team_a
            elif implied_b < 40 and mom_b > 60:
                sg_decision = "BUY_YES"; sg_team = ctx.team_b

            # mm2_v1 decision
            sig = strat_simple.generate_signal(ctx)
            mm2_decision = "SKIP"
            mm2_team = None
            if sig:
                mm2_decision = "BUY_YES"; mm2_team = sig.buy_team

            match = "✓ MATCH" if (sg_decision == mm2_decision and sg_team == mm2_team) else "✗ DIFFER"
            print(f"  {ctx.event_ticker[-20:]}")
            print(f"    implied_a={implied_a:.1f}% wins_a={wins_a}/5 mom_a={mom_a}")
            print(f"    implied_b={implied_b:.1f}% wins_b={wins_b}/5 mom_b={mom_b}")
            print(f"    signal_generator → {sg_decision} {sg_team or ''}")
            print(f"    mm2_v1 (simple)  → {mm2_decision} {mm2_team or ''} {match}")
            print()
