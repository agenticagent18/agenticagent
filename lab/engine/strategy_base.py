"""Abstract base class for all strategies in the strategy lab."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    market_ticker: str
    side: str           # BUY_YES or BUY_NO
    strength: float     # 0-100 (or higher for scaled formulas)
    contracts: int
    reasoning: str
    signal_type: str    # e.g. 'underdog_momentum', 'favorite_vs_hot_opp'
    buy_team: str       # Kalshi team code being bought YES


@dataclass
class GameContext:
    event_ticker: str
    game_date: str          # YYYY-MM-DD
    game_start: object      # datetime
    team_a: str             # Kalshi code
    team_b: str
    mkt_a: str              # full market ticker for team_a
    mkt_b: str
    mid_a: float            # entry midpoint 0-1 (buy_yes = team_a)
    wins_history_a: list    # bool list, most recent first, up to 20 games
    wins_history_b: list
    settlement_a: float     # 0.0 or 1.0 (team_a won)


class StrategyBase(ABC):
    STRATEGY_ID: str = "base"

    def __init__(self, params: dict):
        self.params = {**self.DEFAULT_PARAMS, **params}

    @property
    @abstractmethod
    def DEFAULT_PARAMS(self) -> dict:
        ...

    @abstractmethod
    def generate_signal(self, game_context: GameContext) -> Optional[Signal]:
        """Return a Signal if the game meets criteria, else None."""
        ...

    def size_position(self, signal: Signal, available_cash: float = 50.0) -> int:
        """Return number of contracts based on signal strength and available cash."""
        max_c = self.params.get("max_contracts", 3)
        if signal.strength >= 100:
            return min(3, max_c)
        if signal.strength >= 80:
            return min(2, max_c)
        return min(1, max_c)
