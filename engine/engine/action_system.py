"""Action system — validates and dispatches game actions."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Union

from .actions.base import GameAction, ActionResult
from .actions.quick_actions import (
    OccupyAction, MarchAction, DrawAction, RecruitAction, FortifyAction,
)
from .actions.special_actions import (
    ConvertAction, ArchiveAction, SpreadCultureAction,
    SearchAction, LevyAction, RaiseOrderAction, LowerOrderAction,
    ActivateEffectAction,
)
from .actions.card_actions import PlayCardAction, CourtAction, PublicCardAction
from models.enums import ControlState


# Union type for all possible actions
AnyAction = Union[
    OccupyAction, MarchAction, DrawAction, RecruitAction, FortifyAction,
    ConvertAction, ArchiveAction, SpreadCultureAction,
    SearchAction, LevyAction, RaiseOrderAction, LowerOrderAction,
    ActivateEffectAction,
    PlayCardAction, CourtAction, PublicCardAction,
]


class ActionSystem:
    """Central dispatcher for validating and executing game actions."""

    def validate(self, state: "GameState", action: AnyAction) -> ActionResult:
        """Validate an action against the current game state."""
        return action.validate(state)

    def execute(self, state: "GameState", action: AnyAction) -> ActionResult:
        """Execute a validated action on the game state.

        Returns ActionResult with events. Modifies state in place.
        The caller should check action.success before relying on state changes.
        """
        # Validate first
        result = action.validate(state)
        if not result.success:
            return result

        # Execute
        return action.execute(state)

    def get_available_quick_actions(self, state: "GameState", player_id: str) -> list[GameAction]:
        """Get all currently legal quick actions for a player."""
        player = state.get_player(player_id)
        if not player:
            return []

        available = []

        # Occupy — check for adjacent empty (unoccupied) locations
        # Use adjacency source locations (own; own + Sima with expedition marker).
        # Rulebook: 正常只有自己地点; 北伐标记使司马家地点也作为相邻起点。
        source_locs = state.get_adjacency_source_locations(player_id)
        for loc_id, loc in state.locations.items():
            if loc.controller != ControlState.EMPTY:
                continue
            if any(n in source_locs for n in state.get_adjacent_locations(loc_id)):
                action = OccupyAction(player_id=player_id, target_location=loc_id)
                if action.validate(state).success:
                    available.append(action)

        # March — check for adjacent non-friendly, non-empty locations
        # (NEUTRAL = neutral forces present; EMPTY = unoccupied → use Occupy instead)
        # Use adjacency source locations — consistent with MarchAction.validate().
        for loc_id, loc in state.locations.items():
            cs = state._player_control_state(player_id)
            if loc.is_friendly_to(cs) or loc.controller == ControlState.EMPTY:
                continue
            if any(n in source_locs for n in state.get_adjacent_locations(loc_id)):
                action = MarchAction(player_id=player_id, target_location=loc_id)
                if action.validate(state).success:
                    available.append(action)

        # Draw — once per turn
        if not player.has_drawn_quick and player.military >= 2 and state.main_deck:
            action = DrawAction(player_id=player_id)
            if action.validate(state).success:
                available.append(action)

        # Recruit — always available if you have cards
        if player.hand:
            for i in range(len(player.hand)):
                action = RecruitAction(player_id=player_id, card_to_discard_index=i)
                available.append(action)

        # Fortify — once per turn, can fortify friendly locations (including allies)
        friendly = state.get_friendly_locations(player_id)
        if not player.has_fortified_quick and player.military >= 1:
            for loc_id in friendly:
                loc = state.locations.get(loc_id)
                if loc and not loc.is_fortified:
                    action = FortifyAction(player_id=player_id, target_location=loc_id)
                    if action.validate(state).success:
                        available.append(action)

        return available

    def get_available_hand_actions(self, state: "GameState", player_id: str) -> list[PlayCardAction]:
        """Get all legal hand card play actions."""
        player = state.get_player(player_id)
        if not player or not player.can_take_hand_action():
            return []

        available = []
        for i, card in enumerate(player.hand):
            if not card.definition.is_playable_by(player.faction):
                continue

            # Check play_condition from card's parsed effect
            parsed = card.definition.parsed_effect
            if parsed and parsed.play_condition:
                resolver = getattr(state, 'effect_resolver', None)
                if resolver and not resolver.check_condition(
                    parsed.play_condition, state, player_id):
                    continue

            # For each card, generate possible payment combinations
            cost = card.cost
            base_actions = []
            if cost == 0:
                base_actions.append(PlayCardAction(
                    player_id=player_id, card_index=i, payment_indices=[]
                ))
            else:
                # Generate all combinations of payment cards
                other_indices = [j for j in range(len(player.hand)) if j != i]
                if len(other_indices) >= cost:
                    base_actions.append(PlayCardAction(
                        player_id=player_id, card_index=i,
                        payment_indices=other_indices[:cost]
                    ))

            # Friend cards when staff is full: generate one action per replacement slot
            if card.is_friend and not player.can_play_friend():
                for action in base_actions:
                    for si in range(len(player.staff_area)):
                        available.append(PlayCardAction(
                            player_id=player_id, card_index=action.card_index,
                            payment_indices=list(action.payment_indices),
                            replace_staff_index=si,
                        ))
            else:
                available.extend(base_actions)

        return available

    def get_available_court_actions(self, state: "GameState", player_id: str) -> list[CourtAction]:
        """Get all legal court actions."""
        player = state.get_player(player_id)
        if not player or not player.can_take_court_action():
            return []

        available = []
        court = state.get_court_cards(player_id)
        for card in court:
            if card.definition.is_playable_by(player.faction):
                # Check play_condition from card's parsed effect
                parsed = card.definition.parsed_effect
                if parsed and parsed.play_condition:
                    resolver = getattr(state, 'effect_resolver', None)
                    if resolver and not resolver.check_condition(
                        parsed.play_condition, state, player_id):
                        continue

                action = CourtAction(player_id=player_id, card_id=card.definition.card_id)
                if action.validate(state).success:
                    available.append(action)

        return available

    def get_available_public_actions(self, state: "GameState", player_id: str) -> list[PublicCardAction]:
        """Get all legal public action card plays."""
        player = state.get_player(player_id)
        if not player or not player.can_take_hand_action():
            return []

        available = []
        for card in state.public_action_pool:
            defn = card.definition
            if defn.card_id in state.public_exhausted:
                continue
            if not defn.is_playable_by(player.faction):
                continue

            # Check play_condition from card's parsed effect
            parsed = defn.parsed_effect
            if parsed and parsed.play_condition:
                resolver = getattr(state, 'effect_resolver', None)
                if resolver and not resolver.check_condition(
                    parsed.play_condition, state, player_id):
                    continue

            # Generate payment combinations
            cost = card.cost
            if cost == 0:
                available.append(PublicCardAction(
                    player_id=player_id, card_id=defn.card_id, payment_indices=[]
                ))
            else:
                other_indices = [j for j in range(len(player.hand))]
                if len(other_indices) >= cost:
                    available.append(PublicCardAction(
                        player_id=player_id, card_id=defn.card_id,
                        payment_indices=other_indices[:cost],
                    ))

        return available

    def get_available_activate_actions(self, state: "GameState", player_id: str) -> list[ActivateEffectAction]:
        """Get all legal active ability activation actions.

        Scans player's hero card and staff_area cards for active abilities
        (ability_type == "active") that haven't been activated this turn.
        """
        player = state.get_player(player_id)
        if not player:
            return []

        available = []

        # Scan hero card
        if player.hero:
            available.extend(self._build_activate_actions(
                player, player.hero, state))

        # Scan staff area
        for card in player.staff_area:
            available.extend(self._build_activate_actions(
                player, card, state))

        return available

    def _build_activate_actions(self, player: "PlayerState", card: "Card",
                                state: "GameState") -> list[ActivateEffectAction]:
        """Build ActivateEffectAction instances for a card's active abilities."""
        available = []
        card_id = card.definition.card_id

        # Skip if already activated this turn
        if card_id in player.activated_card_ids:
            return available

        parsed = card.definition.parsed_effect
        if not parsed:
            return available

        active_blocks = [b for b in parsed.blocks if b.ability_type == "active"]
        for bi, block in enumerate(active_blocks):
            # If the block has choice_options, generate one action per choice
            if block.choice_options:
                for ci in range(len(block.choice_options)):
                    action = ActivateEffectAction(
                        player_id=player.player_id,
                        card_id=card_id,
                        block_index=bi,
                        choice_index=ci,
                    )
                    if action.validate(state).success:
                        available.append(action)
            else:
                action = ActivateEffectAction(
                    player_id=player.player_id,
                    card_id=card_id,
                    block_index=bi,
                    choice_index=0,
                )
                if action.validate(state).success:
                    available.append(action)

        return available
