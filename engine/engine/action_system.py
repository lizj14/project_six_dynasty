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
from models.enums import ControlState, CardType


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

    def __init__(self):
        self.on_executed: callable = None  # fn(action, state, player_id, result)

    def validate(self, state: "GameState", action: AnyAction) -> ActionResult:
        """Validate an action against the current game state."""
        return action.validate(state)

    def execute(self, state: "GameState", action: AnyAction) -> ActionResult:
        """Execute a validated action on the game state.

        Returns ActionResult with events. Modifies state in place.
        The caller should check action.success before relying on state changes.
        Fires on_executed callback on success so passive triggers are
        dispatched even when actions are executed inside card effects.
        """
        # Validate first
        result = action.validate(state)
        if not result.success:
            return result

        # Execute
        result = action.execute(state)

        # Fire on_executed callback for passive trigger dispatch
        if result.success and self.on_executed:
            self.on_executed(action, state,
                             getattr(action, 'player_id', ''),
                             result)

        return result

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
        sima_available = False
        from rules.sima import can_place_sima_army
        from models.enums import FactionType
        if player.faction == FactionType.JIN and can_place_sima_army(state):
            sima_available = True

        for loc_id, loc in state.locations.items():
            if loc.controller != ControlState.EMPTY:
                continue
            if any(n in source_locs for n in state.get_adjacent_locations(loc_id)):
                # Regular occupy (own army)
                action = OccupyAction(player_id=player_id, target_location=loc_id)
                if action.validate(state).success:
                    available.append(action)
                # Sima army occupy (Jin only, uses Sima's military/reserves)
                if sima_available:
                    sima_action = OccupyAction(player_id=player_id, target_location=loc_id,
                                               use_sima_army=True)
                    if sima_action.validate(state).success:
                        available.append(sima_action)

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
        extra_filter = getattr(player, 'extra_hand_action_filter', None)
        for i, card in enumerate(player.hand):
            if not card.definition.is_playable_by(player.faction):
                continue

            # If extra hand action has a card_type filter, only show matching cards
            # ("any" means no filter — don't block any card type)
            if extra_filter and extra_filter != "any":
                card_type_matches = (
                    extra_filter == "friend" and card.definition.is_friend or
                    extra_filter == "strategy" and card.definition.card_type == CardType.STRATEGY or
                    extra_filter == "event" and card.definition.card_type == CardType.EVENT
                )
                if not card_type_matches:
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

    def get_available_court_cards(self, state: "GameState", player_id: str) -> list:
        """Get court cards that pass faction + play_condition checks.

        Shared between get_available_court_actions (normal court menu) and
        the extra_action_granted handler (extra court action prompt).
        """
        player = state.get_player(player_id)
        if not player:
            return []
        resolver = getattr(state, 'effect_resolver', None)
        result = []
        for card in state.get_court_cards(player_id):
            if not card.definition.is_playable_by(player.faction):
                continue
            parsed = card.definition.parsed_effect
            if parsed and parsed.play_condition:
                if resolver and not resolver.check_condition(
                    parsed.play_condition, state, player_id):
                    continue
            result.append(card)
        return result

    def get_available_court_actions(self, state: "GameState", player_id: str) -> list[CourtAction]:
        """Get all legal court actions."""
        player = state.get_player(player_id)
        if not player or not player.can_take_court_action():
            return []

        available = []
        for card in self.get_available_court_cards(state, player_id):
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
