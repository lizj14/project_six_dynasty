"""Effect resolver — walks the CardEffect AST and executes against GameState."""

from typing import Optional, Any
from dataclasses import dataclass, field

from .effect_ast import (
    CardEffect, AbilityBlock, EffectStep,
    EffectType, AbilityType, TriggerType,
)


@dataclass
class ResolveResult:
    """Result of resolving a card effect."""
    success: bool = True
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class EffectResolver:
    """Resolves parsed CardEffect AST nodes against a GameState.

    Uses the action system to execute concrete actions (march, occupy, etc.)
    and handles resource changes (military, VP) directly.
    """

    def __init__(self, action_system=None):
        self.action_system = action_system

    def resolve(self, effect: CardEffect, state: "GameState",
                player_id: str, context: dict = None) -> ResolveResult:
        """Resolve a complete card effect for a given player.

        Args:
            effect: Parsed CardEffect
            state: Current game state (mutated in place)
            player_id: The player executing the card
            context: Additional context (e.g. card index, target selections)
        """
        result = ResolveResult()

        for block in effect.blocks:
            block_result = self._resolve_block(block, state, player_id, context)
            result.events.extend(block_result.events)
            result.errors.extend(block_result.errors)
            if not block_result.success:
                result.success = False

        return result

    def _resolve_block(self, block: AbilityBlock, state: "GameState",
                       player_id: str, context: dict = None) -> ResolveResult:
        """Resolve a single ability block."""
        result = ResolveResult()

        # Handle strategy action (牌组行动) — these are resource gains
        if block.ability_type == AbilityType.STRATEGY_ACTION:
            for step in block.steps:
                step_result = self._execute_step(step, state, player_id, context)
                result.events.extend(step_result.events)
                result.errors.extend(step_result.errors)
            return result

        # Handle choice blocks
        if block.choice_options:
            # The AI/human should have chosen an option; default to first
            choice_idx = 0
            if context and 'choice_index' in context:
                choice_idx = context['choice_index']
            if choice_idx < len(block.choice_options):
                for step in block.choice_options[choice_idx]:
                    step_result = self._execute_step(step, state, player_id, context)
                    result.events.extend(step_result.events)
            return result

        # Regular steps
        for step in block.steps:
            step_result = self._execute_step(step, state, player_id, context)
            result.events.extend(step_result.events)
            result.errors.extend(step_result.errors)

        # Usurp steps (if player has usurp privilege)
        if block.usurp_steps and self._can_usurp(state, player_id):
            for step in block.usurp_steps:
                step_result = self._execute_step(step, state, player_id, context)
                result.events.extend(step_result.events)

        return result

    def _execute_step(self, step: EffectStep, state: "GameState",
                      player_id: str, context: dict = None) -> ResolveResult:
        """Execute a single effect step."""
        result = ResolveResult()

        # Check condition
        if step.condition and not self._check_condition(step.condition, state, player_id):
            return result

        player = state.get_player(player_id)
        et = step.effect_type
        p = step.params

        if et == EffectType.GAIN_MILITARY:
            amount = self._resolve_value(p.get("amount", 0), state, player_id)
            if player:
                player.military += amount
                result.events.append({"type": "gain_military", "amount": amount})

        elif et == EffectType.GAIN_VP:
            amount = self._resolve_value(p.get("amount", 0), state, player_id)
            if player:
                player.vp += amount
                result.events.append({"type": "gain_vp", "amount": amount})
                if player.vp >= 150:
                    state.game_end_marker = player_id
                    state.game_end_reason = "150vp"

        elif et == EffectType.PAY_MILITARY:
            amount = p.get("amount", 0)
            if player:
                player.military = max(0, player.military - amount)

        elif et == EffectType.PAY_VP:
            amount = p.get("amount", 0)
            if player:
                player.vp = max(0, player.vp - amount)

        elif et == EffectType.DRAW_CARDS:
            count = p.get("count", 1)
            for _ in range(count):
                if state.main_deck:
                    card = state.main_deck.pop(0)
                    if player:
                        player.hand.append(card)
                    result.events.append({"type": "draw", "card": card.name})

        elif et == EffectType.DISCARD_CARDS:
            count = p.get("count", 1)
            for _ in range(count):
                if player and player.hand:
                    state.main_discard.append(player.hand.pop())

        elif et == EffectType.ARCHIVE_THIS:
            # Card archives itself — handled by the caller via card reference
            result.events.append({"type": "archive_this"})

        elif et == EffectType.ARCHIVE_CARD:
            count = p.get("count", 1)
            for _ in range(count):
                if player and player.hand:
                    card = player.hand.pop()
                    player.history_area.append(card)
                    player.vp += card.definition.history_vp
                    # Jin gains contribution
                    from ..models.enums import FactionType
                    if player.faction == FactionType.JIN:
                        player.contribution = min(9, player.contribution + 1)

        elif et == EffectType.CONVERT:
            # Use ConvertAction from action system
            if self.action_system:
                from ..engine.actions.special_actions import ConvertAction
                locs = p.get("specific_locations", [])
                count = p.get("count", len(locs))
                restriction = p.get("restriction", [])
                for loc_id in locs[:count]:
                    action = ConvertAction(
                        player_id=player_id,
                        target_location=loc_id,
                        neutral_only=('neutral' in restriction),
                    )
                    r = self.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])

        elif et == EffectType.SPREAD_CULTURE:
            if self.action_system:
                from ..engine.actions.special_actions import SpreadCultureAction
                culture = p.get("culture")
                if culture:
                    action = SpreadCultureAction(
                        player_id=player_id,
                        culture_type=culture,
                        target_region="",  # Generic — region selection needed
                    )
                    r = self.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])

        elif et == EffectType.SEARCH:
            if self.action_system:
                from ..engine.actions.special_actions import SearchAction
                action = SearchAction(
                    player_id=player_id,
                    search_count=p.get("count", 1),
                    search_type=p.get("search_type", ""),
                )
                r = self.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])

        elif et == EffectType.MARCH:
            if self.action_system:
                from ..engine.actions.quick_actions import MarchAction
                count = p.get("count", 1)
                free = p.get("free", False)
                for _ in range(count):
                    # March needs target selection — for now, just note it
                    result.events.append({"type": "march_requested", "free": free})

        elif et == EffectType.FORTIFY:
            if self.action_system:
                from ..engine.actions.quick_actions import FortifyAction
                count = p.get("count", 1)
                free = p.get("free", False)
                for _ in range(count):
                    result.events.append({"type": "fortify_requested", "free": free})

        elif et == EffectType.RAISE_ORDER:
            if self.action_system:
                from ..engine.actions.special_actions import RaiseOrderAction
                action = RaiseOrderAction(
                    player_id=player_id,
                    amount=p.get("amount", 1),
                )
                r = self.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])

        elif et == EffectType.LOWER_ORDER:
            if self.action_system:
                from ..engine.actions.special_actions import LowerOrderAction
                target = p.get("target_player", player_id)
                action = LowerOrderAction(
                    player_id=player_id,
                    target_player_id=target,
                    amount=p.get("amount", 1),
                )
                r = self.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])

        elif et == EffectType.DRAFT:
            # 征发 — handled via card context
            result.events.append({"type": "draft_requested",
                                  "count": p.get("count", 1)})

        elif et == EffectType.SUPPLY_COURT:
            count = p.get("count", 1)
            deck = state.get_national_deck(player_id)
            court = state.get_court_cards(player_id)
            for _ in range(count):
                if deck:
                    court.append(deck.pop(0))
            result.events.append({"type": "supply_court", "count": count})

        elif et == EffectType.GET_EXPEDITION:
            if player:
                player.has_expedition_marker = True
                result.events.append({"type": "expedition_gained"})

        elif et == EffectType.ADD_REFUGEE:
            from ..models.card import CardLibrary
            count = p.get("count", 1)

        elif et == EffectType.RAISE_CULTURE_LEVEL:
            culture = p.get("culture")
            amount = p.get("amount", 1)
            if player and culture:
                from ..models.enums import CultureType
                ct = CultureType(culture)
                current = player.culture_contributions.get(ct, 0)
                player.culture_contributions[ct] = min(10, current + amount)

        elif et == EffectType.RAW:
            result.events.append({"type": "raw_effect", "text": step.source_text})

        return result

    def _resolve_value(self, value: Any, state: "GameState", player_id: str) -> int:
        """Resolve a value that might be a variable (X) or literal number."""
        if isinstance(value, int):
            return value
        if value == 'X':
            # X is resolved based on context — for now return 0
            # The actual resolution depends on the card's specific formula
            return 0
        return int(value) if value else 0

    def _can_usurp(self, state: "GameState", player_id: str) -> bool:
        """Check if a Jin player can execute usurp effects."""
        player = state.get_player(player_id)
        if not player:
            return False
        from ..models.enums import FactionType
        if player.faction != FactionType.JIN:
            return False
        # Must have higher prestige than other Jin players AND Sima
        other_prestige = []
        for p in state.get_jin_players():
            if p.player_id != player_id:
                other_prestige.append(p.prestige)
        other_prestige.append(state.sima.prestige)
        return all(player.prestige > op for op in other_prestige)

    def _check_condition(self, condition: "Condition", state: "GameState",
                         player_id: str) -> bool:
        """Check if a condition is met."""
        # Simplified condition checking
        return True
