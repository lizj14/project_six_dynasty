"""DummyAI — weighted-random AI that prefers map actions when military is available.

Makes randomized but sensible choices:
  - Prioritizes march/occupy/spread_culture when military allows
  - Falls back to court actions and other quick actions
  - All filtering is done by the engine via ActionSystem.get_available_*
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from .interface import GameAgent, SetupContext, SetupDecision
from models.enums import ControlState, TerrainType


# ── Recruit heuristic helper ──────────────────────────────────────

def _can_march_after_recruit(state: "GameState", player_id: str,
                             military: int) -> bool:
    """Check whether the player could march after gaining +1 military.

    Scans all potential march targets (enemy locations adjacent to
    friendly) and checks if any have cost ≤ military + 1.
    """
    new_military = military + 1
    friendly = state.get_friendly_locations(player_id)
    player_cs = state._player_control_state(player_id)

    for loc_id, loc in state.locations.items():
        # Skip friendly or neutral locations (march targets must be enemy)
        if loc.is_friendly_to(player_cs) or loc.controller == ControlState.NEUTRAL:
            continue

        # Must be adjacent to a friendly location
        neighbors = state.get_adjacent_locations(loc_id)
        if not any(n in friendly for n in neighbors):
            continue

        # Calculate march cost
        cost = 3  # base

        # Difficult terrain: +1
        for nb in neighbors:
            if nb in friendly:
                terrain = state.get_terrain(nb, loc_id)
                if terrain == TerrainType.DIFFICULT:
                    cost += 1
                break

        # Fortified target: +1
        if loc.is_fortified:
            cost += 1

        # Isolated location: -1
        target_cs = loc.controller
        isolated = True
        for nb in neighbors:
            nb_loc = state.locations.get(nb)
            if nb_loc and nb_loc.is_friendly_to(target_cs):
                isolated = False
                break
        if isolated:
            cost -= 1

        cost = max(1, cost)

        if new_military >= cost:
            return True

    return False


# ── Action category helper ────────────────────────────────────────

def _action_category(action) -> str:
    """Classify an action into a broad category for weighted sampling."""
    atype = getattr(action, 'action_type', '')
    if atype in ("march",):
        return "march"
    if atype in ("occupy",):
        return "occupy"
    if atype in ("spread_culture", "convert"):
        return "culture"
    if atype in ("fortify",):
        return "fortify"
    if atype in ("play_card",):
        return "play_card"
    if atype in ("court_action",):
        return "court_action"
    if atype in ("recruit", "draw", "archive", "raise_order",
                 "lower_order", "search", "levy"):
        return "quick"
    return "other"


class DummyAI(GameAgent):
    """Weighted-random AI: prefers map actions when military available."""

    def __init__(self, player_id: str = "", seed: int = 0):
        self.player_id = player_id
        self.rng = random.Random(seed)
        self._recruit_count: int = 0
        self._last_round: int = -1

    # === Setup ===

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """Randomly pick hero, goals, and face-down card."""
        d = SetupDecision()
        d.hero_index = self.rng.randint(0, len(ctx.hero_choices) - 1) if ctx.hero_choices else 0

        if ctx.goal_choices:
            indices = list(range(len(ctx.goal_choices)))
            self.rng.shuffle(indices)
            d.public_goal_index = indices[0]
            d.secret_goal_index = indices[1] if len(indices) >= 2 else indices[0]

        if ctx.hand_cards:
            d.face_down_card_index = self.rng.randint(0, len(ctx.hand_cards) - 1)
            other = [i for i in range(len(ctx.hand_cards)) if i != d.face_down_card_index]
            self.rng.shuffle(other)
            d.payment_indices = other[:2]

        return d

    # === Turn: iterative single-action decision ===

    def decide_action(self, state: "GameState",
                      available_actions: list) -> Optional["GameAction"]:
        """Weighted-random action selection.

        Prefers map actions (march, occupy, spread_culture) when military
        is available, with fallback to court actions and quick actions.

        Dummy AI heuristics (not game rules):
          - Maximum 2 recruits per turn
          - Only recruit if march actions are available (recruiting just
            to discard cards with no follow-up march is wasteful)

        Returns None to pass (end turn) when:
          - No actions available, or
          - Randomly decides to stop (5-10% chance per call).
        """
        if not available_actions:
            return None

        # Reset per-turn tracking if round changed
        if state.round != self._last_round:
            self._last_round = state.round
            self._recruit_count = 0

        player = state.get_player(self.player_id)
        military = player.military if player else 0

        # ── Dummy AI recruit filtering ────────────────────
        # Only consider recruit if: (a) < 2 this turn, and
        # (b) marching is possible with military after recruiting
        can_march = _can_march_after_recruit(state, self.player_id, military)
        filtered_actions = []
        for a in available_actions:
            if getattr(a, 'action_type', '') == "recruit":
                if self._recruit_count >= 2:
                    continue          # Rule: max 2 per turn
                if not can_march:
                    continue          # Heuristic: won't recruit if still can't march
            filtered_actions.append(a)

        available_actions = filtered_actions
        if not available_actions:
            return None

        # 5-10% chance to stop early, simulating "pass"
        pass_chance = 0.05 if military > 0 else 0.15
        if self.rng.random() < pass_chance:
            return None

        # ── Weighted selection ──────────────────────────
        # Group actions by category
        by_cat: dict[str, list] = {}
        for a in available_actions:
            cat = _action_category(a)
            by_cat.setdefault(cat, []).append(a)

        # Determine category weights based on military available
        if military >= 3:
            weights = {
                "march": 4.0,     # Priority: take territory
                "occupy": 3.0,
                "culture": 2.5,
                "play_card": 2.0,
                "fortify": 1.5,
                "court_action": 1.0,
                "quick": 0.3,
                "other": 0.5,
            }
        elif military >= 1:
            weights = {
                "occupy": 3.5,
                "march": 3.0,     # Can still march if affordable
                "culture": 2.5,
                "play_card": 2.0,
                "fortify": 2.0,
                "court_action": 1.5,
                "quick": 0.5,
                "other": 0.5,
            }
        else:
            # No military — can't march/occupy/fortify anyway,
            # but those won't appear in available_actions
            weights = {
                "play_card": 3.0,
                "culture": 2.0,
                "court_action": 2.0,
                "quick": 1.0,
                "march": 0.0,
                "occupy": 0.0,
                "fortify": 0.0,
                "other": 0.5,
            }

        # Build weighted pool
        pool: list = []
        for cat, actions in by_cat.items():
            w = weights.get(cat, 0.5)
            # Repeat each action in the pool proportionally to its weight
            count = max(1, int(w * 10))
            pool.extend(actions * count)

        if not pool:
            return self.rng.choice(available_actions)

        chosen = self.rng.choice(pool)

        # Track recruit count
        if getattr(chosen, 'action_type', '') == "recruit":
            self._recruit_count += 1

        return chosen

    def take_turn(self, state: "GameState") -> list:
        """Legacy batch interface — returns empty, engine uses decide_action."""
        return []

    # === Choice methods ===

    def make_choice(self, state: "GameState", prompt: dict) -> int:
        options = prompt.get("options", [])
        return self.rng.randint(0, len(options) - 1) if options else 0

    def select_target(self, state: "GameState", prompt: dict) -> Optional[str]:
        options = prompt.get("options", [])
        return self.rng.choice(options) if options else None

    def choose_discards(self, state: "GameState", hand_cards: list[str],
                        count: int) -> list[int]:
        """Randomly pick cards to discard."""
        indices = list(range(len(hand_cards)))
        self.rng.shuffle(indices)
        return indices[:count]
