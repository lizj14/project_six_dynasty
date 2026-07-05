"""GameAgent abstract base class — pluggable decision-maker for game engine.

The engine calls the agent at two decision points:
  1. setup_decision() — once at game start (hero, goals, initial card)
  2. take_turn() — once per round (court, hand, quick actions)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SetupContext:
    """All information the agent needs to make setup decisions."""
    player_id: str
    faction: str                        # "north" or "jin"
    hero_choices: list[dict] = field(default_factory=list)
    # Each hero: {"name": str, "faction": str, "start_order": int,
    #             "effect_text": str, "category": str}
    goal_choices: list[dict] = field(default_factory=list)
    # Each goal: {"name": str, "simple_vp": int, "full_vp": int,
    #             "simple_condition": str, "full_condition": str}
    hand_cards: list[str] = field(default_factory=list)
    # Card names in current hand (hero starting cards + initial draws)
    # Jin only: additional info
    other_jin_heroes: list[str] = field(default_factory=list)
    # Names of heroes already taken by other Jin players (for coordination)


@dataclass
class SetupDecision:
    """The agent's complete setup choices."""
    hero_index: int = 0                 # Index into hero_choices
    public_goal_index: int = 0          # Index into goal_choices (Jin only)
    secret_goal_index: int = -1         # -1 = same as public (if only 1 available)
    face_down_card_index: int = 0       # Which card to play face-down (index in hand)
    payment_indices: list[int] = field(default_factory=list)
    # Which other hand cards to use as payment


class GameAgent(ABC):
    """Interface for both human and AI decision-makers."""

    player_id: str = ""

    # ======== Setup (once per game) ========

    @abstractmethod
    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """Make all setup decisions at once given full context.

        Called once per player during game setup.
        The agent sees hero options, goal options (if Jin), and initial hand.
        """
        ...

    # ======== Turn (once per round) ========

    @abstractmethod
    def take_turn(self, state: "GameState") -> list["GameAction"]:
        """Given current game state, produce the sequence of actions."""
        ...

    @abstractmethod
    def make_choice(self, state: "GameState", prompt: dict) -> int:
        """Called when a card effect requires choosing from options.

        Returns the index of the chosen option (0-based).
        """
        ...

    @abstractmethod
    def select_target(self, state: "GameState", prompt: dict) -> Optional[str]:
        """Called when a player must select a target (location, player, card).

        Returns the selected target identifier.
        """
        ...
