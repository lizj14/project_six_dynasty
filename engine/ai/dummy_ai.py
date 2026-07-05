"""DummyAI — rule-based AI with randomized choices for varied testing.

Makes legal but random choices. Spends all military before ending turn.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from .interface import GameAgent, SetupContext, SetupDecision


class DummyAI(GameAgent):
    """Rule-based AI with random selection from valid options."""

    def __init__(self, player_id: str = "", seed: int = 0):
        self.player_id = player_id
        self.rng = random.Random(seed)

    # === Setup (unified) ===

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """Randomly pick hero, goals, and face-down card."""
        d = SetupDecision()
        d.hero_index = self.rng.randint(0, len(ctx.hero_choices) - 1) if ctx.hero_choices else 0

        if ctx.goal_choices:
            indices = list(range(len(ctx.goal_choices)))
            self.rng.shuffle(indices)
            d.public_goal_index = indices[0]
            d.secret_goal_index = indices[1] if len(indices) >= 2 else indices[0]

        # Face-down card: pick a card, find payment from other cards
        if ctx.hand_cards:
            d.face_down_card_index = self.rng.randint(0, len(ctx.hand_cards) - 1)
            # Simulate cost — for now just pick random other cards for payment
            # (the engine will validate; if insufficient payment, it falls back to discard)
            other = [i for i in range(len(ctx.hand_cards)) if i != d.face_down_card_index]
            self.rng.shuffle(other)
            d.payment_indices = other[:2]  # Assume cost ≤ 2

        return d

    # === Turn decisions ===

    def take_turn(self, state: "GameState") -> list:
        """Produce a sequence of actions for this turn."""
        actions = []
        player = state.get_player(self.player_id)
        if not player:
            return actions

        # 1. Court action — random from valid
        court_action = self._pick_court_action(state, player)
        if court_action:
            actions.append(court_action)

        # 2. Hand action — random from valid
        hand_action = self._pick_hand_action(state, player)
        if hand_action:
            actions.append(hand_action)

        # 3. Quick actions — use all military
        quick = self._pick_quick_actions(state, player)
        actions.extend(quick)

        return actions

    # === Internal methods ===

    def _pick_court_action(self, state, player) -> Optional["CourtAction"]:
        """Randomly pick a valid court card."""
        if player.has_taken_court_action:
            return None

        from engine.actions.card_actions import CourtAction
        court = state.get_court_cards(self.player_id)

        valid = []
        for card in court:
            if not card.definition.is_playable_by(player.faction):
                continue
            action = CourtAction(player_id=self.player_id,
                                  card_id=card.definition.card_id)
            if action.validate(state).success:
                valid.append(action)

        return self.rng.choice(valid) if valid else None

    def _pick_hand_action(self, state, player) -> Optional["PlayCardAction"]:
        """Randomly pick a playable card from hand."""
        if player.has_taken_hand_action or not player.hand:
            return None

        from engine.actions.card_actions import PlayCardAction

        valid = []
        for idx, card in enumerate(player.hand):
            if not card.definition.is_playable_by(player.faction):
                continue
            if card.is_friend and not player.can_play_friend():
                continue

            cost = card.cost
            other_indices = [i for i in range(len(player.hand)) if i != idx]
            self.rng.shuffle(other_indices)

            if len(other_indices) >= cost:
                payment = other_indices[:cost]
                action = PlayCardAction(
                    player_id=self.player_id,
                    card_index=idx,
                    payment_indices=payment,
                )
                if action.validate(state).success:
                    valid.append(action)

        return self.rng.choice(valid) if valid else None

    def _pick_quick_actions(self, state, player) -> list:
        """Generate quick actions — loop until military spent or no moves."""
        actions = []
        mil = player.military

        # Track targets already used this turn to avoid repeats
        used_targets: set[str] = set()
        drew = False
        fortified = False

        max_iterations = 50
        for _ in range(max_iterations):
            if mil <= 0:
                break

            action = None
            action_cost = 0

            # Priority 1: March
            marches = self._find_march_actions(state, player, mil)
            marches = [m for m in marches if m.target_location not in used_targets]
            if marches:
                ma = self.rng.choice(marches)
                cost = ma._calculate_cost(state)
                if mil >= cost:
                    action = ma
                    action_cost = cost
                    used_targets.add(ma.target_location)

            # Priority 2: Occupy
            if not action:
                occupies = self._find_occupy_actions(state, player, mil)
                occupies = [o for o in occupies if o.target_location not in used_targets]
                if occupies:
                    action = self.rng.choice(occupies)
                    action_cost = 1
                    used_targets.add(action.target_location)

            # Priority 3: Draw (once)
            if not action and not drew and mil >= 2 and state.main_deck:
                from engine.actions.quick_actions import DrawAction
                da = DrawAction(player_id=self.player_id)
                if da.validate(state).success:
                    action = da
                    action_cost = 2
                    drew = True

            # Priority 4: Fortify (once)
            if not action and not fortified and mil >= 1:
                from engine.actions.quick_actions import FortifyAction
                friendly = state.get_friendly_locations(self.player_id)
                fort_locs = [lid for lid in friendly
                             if not state.locations[lid].is_fortified
                             and lid not in used_targets]
                if fort_locs:
                    fa = FortifyAction(
                        player_id=self.player_id,
                        target_location=self.rng.choice(fort_locs),
                    )
                    if fa.validate(state).success:
                        action = fa
                        action_cost = 1
                        fortified = True

            # Priority 5: Recruit
            if not action and len(player.hand) > 3:
                from engine.actions.quick_actions import RecruitAction
                idx = self.rng.randint(0, len(player.hand) - 1)
                ra = RecruitAction(player_id=self.player_id, card_to_discard_index=idx)
                if ra.validate(state).success:
                    player.hand.pop(idx)
                    mil += 1
                    actions.append(ra)
                    continue

            if action:
                actions.append(action)
                mil -= action_cost
            else:
                break

        return actions

    def _find_march_actions(self, state, player, mil) -> list:
        """Find all valid march targets."""
        from engine.actions.quick_actions import MarchAction
        from models.enums import ControlState

        if mil < 3:
            return []

        friendly = state.get_friendly_locations(self.player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            cs = state._player_control_state(self.player_id)
            if loc.is_friendly_to(cs):
                continue
            # Can march on enemy AND neutral-occupied locations
            if any(n in friendly for n in state.get_adjacent_locations(loc_id)):
                action = MarchAction(player_id=self.player_id, target_location=loc_id)
                if action.validate(state).success:
                    valid.append(action)
        return valid

    def _find_occupy_actions(self, state, player, mil) -> list:
        """Find all valid occupy targets (only EMPTY locations)."""
        from engine.actions.quick_actions import OccupyAction
        from models.enums import ControlState

        if mil < 1:
            return []

        friendly = state.get_friendly_locations(self.player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            if loc.controller != ControlState.EMPTY:
                continue
            if any(n in friendly for n in state.get_adjacent_locations(loc_id)):
                action = OccupyAction(player_id=self.player_id, target_location=loc_id)
                if action.validate(state).success:
                    valid.append(action)
        return valid

    # === Choice methods ===

    def make_choice(self, state: "GameState", prompt: dict) -> int:
        options = prompt.get("options", [])
        return self.rng.randint(0, len(options) - 1) if options else 0

    def select_target(self, state: "GameState", prompt: dict) -> Optional[str]:
        options = prompt.get("options", [])
        return self.rng.choice(options) if options else None
