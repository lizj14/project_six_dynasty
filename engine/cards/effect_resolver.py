"""Effect resolver — walks the CardEffect AST and executes against GameState.

Uses the Strategy pattern: each effect_type is handled by a dedicated operator
class registered in effect_operators.OPERATOR_REGISTRY.
"""

from typing import Optional, Any
from dataclasses import dataclass, field

from .effect_ast import (
    CardEffect, AbilityBlock, EffectStep,
    AbilityType, Condition,
)
from .effect_operators import OPERATOR_REGISTRY
from .condition_operators import CONDITION_REGISTRY


@dataclass
class ResolveResult:
    """Result of resolving a card effect."""
    success: bool = True
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class EffectResolver:
    """Resolves parsed CardEffect AST nodes against a GameState.

    Uses the action system to execute concrete actions (march, occupy, etc.)
    and dispatches each effect_type to a registered EffectOperator.
    """

    def __init__(self, action_system=None):
        self.action_system = action_system
        self.trigger_callback = None       # Set by GameEngine: fn(trigger_type, context)
        self.log_callback = None           # Set by GameEngine: fn(player_id, effect_type, params, events, source)
        self.select_target_callback = None # Set by GameEngine: fn(player_id, prompt) -> Optional[str]
        self.make_choice_callback = None   # Set by GameEngine: fn(player_id, prompt) -> int

    # ================================================================
    # Public API
    # ================================================================

    def resolve(self, effect: CardEffect, state: "GameState",
                player_id: str, context: dict = None,
                exclude_ability_types: set[str] = None) -> ResolveResult:
        """Resolve a complete card effect for a given player.

        Args:
            effect: Parsed CardEffect
            state: Current game state (mutated in place)
            player_id: The player executing the card
            context: Additional context (e.g. card index, target selections)
            exclude_ability_types: Optional set of ability types to skip
                (e.g. {"active"} when playing a friend card — active
                abilities must be activated explicitly during the turn).
        """
        result = ResolveResult()
        exclude = exclude_ability_types or set()

        for block in effect.blocks:
            if block.ability_type in exclude:
                continue
            block_result = self._resolve_block(block, state, player_id, context)
            result.events.extend(block_result.events)
            result.errors.extend(block_result.errors)
            if not block_result.success:
                result.success = False

        return result

    # ================================================================
    # Block-level resolution
    # ================================================================

    def _resolve_block(self, block: AbilityBlock, state: "GameState",
                       player_id: str, context: dict = None) -> ResolveResult:
        """Resolve a single ability block."""
        result = ResolveResult()

        # Pay block-level costs first
        player = state.get_player(player_id)
        for cost in block.costs:
            if cost.cost_type == "discard_cards":
                count = cost.params.get("count", 1)
                if player and len(player.hand) < count:
                    result.errors.append(
                        f"Not enough hand cards to pay cost: need {count}, have {len(player.hand)}")
                    return result
                for _ in range(count):
                    if player and player.hand:
                        discarded = player.hand.pop()
                        state.main_discard.append(discarded)
                        result.events.append({"type": "pay_discard",
                                             "card": discarded.name})
            elif cost.cost_type == "pay_military":
                amount = cost.params.get("amount", 0)
                if player:
                    if player.military < amount:
                        result.errors.append(
                            f"Not enough military to pay cost: need {amount}, have {player.military}")
                        return result
                    player.military -= amount
                    result.events.append({"type": "pay_military", "amount": amount})
            elif cost.cost_type == "pay_vp":
                amount = cost.params.get("amount", 0)
                if player:
                    if player.vp < amount:
                        result.errors.append(
                            f"Not enough VP to pay cost: need {amount}, have {player.vp}")
                        return result
                    player.vp -= amount
                    result.events.append({"type": "pay_vp", "amount": amount})

        # Handle strategy action (牌组行动) — these are resource gains
        if block.ability_type == AbilityType.STRATEGY_ACTION:
            for step in block.steps:
                step_result = self._execute_step(step, state, player_id, context)
                result.events.extend(step_result.events)
                result.errors.extend(step_result.errors)
            return result

        # Handle choice blocks
        if block.choice_options:
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
            self._fire_trigger("on_usurp", player_id)

        return result

    def _fire_trigger(self, trigger_type: str, player_id: str, context: dict = None):
        """Notify the engine that a sub-effect event occurred (e.g. gain_vp).

        The engine's trigger_callback scans all in-play passives and fires
        any that match this trigger_type.
        """
        if self.trigger_callback:
            ctx = {"player_id": player_id}
            if context:
                ctx.update(context)
            self.trigger_callback(trigger_type, ctx)

    # ================================================================
    # Step dispatch (thin — delegates to operators)
    # ================================================================

    def _execute_step(self, step: EffectStep, state: "GameState",
                      player_id: str, context: dict = None) -> ResolveResult:
        """Execute a single effect step by dispatching to its operator."""
        # Check condition before executing
        if step.condition and not self._check_condition(step.condition, state, player_id):
            return ResolveResult()

        operator = OPERATOR_REGISTRY.get(step.effect_type)
        if operator is None:
            return ResolveResult(
                success=False,
                errors=[f"Unknown effect_type: {step.effect_type}"],
            )

        result = operator.execute(step, state, player_id, context, self)

        # Log this effect execution for state modification tracking
        if self.log_callback and result.success:
            source = "passive" if context and context.get("trigger_type") else "card"
            self.log_callback(player_id, step.effect_type,
                            step.params, result.events, source)

        return result

    # ================================================================
    # Shared utilities (used by operators via resolver.*)
    # ================================================================

    def _resolve_value(self, value: Any, state: "GameState", player_id: str,
                       step_params: dict = None) -> int:
        """Resolve a value that might be a variable, literal, or X-reference."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            player = state.get_player(player_id)
            from models.enums import MarkerType

            # ── X: resolve from step_params metadata ────────────────
            if value == 'X' and step_params:
                source = step_params.get('variable_source', '')
                cap = step_params.get('max')
                if source:
                    marker_map = {'军事': 'marker_count_military',
                                  '文化': 'marker_count_culture',
                                  '内政': 'marker_count_affair',
                                  '权谋': 'marker_count_power'}
                    source_key = marker_map.get(source, source)
                    result = self._resolve_value(source_key, state, player_id)
                    if cap is not None:
                        result = min(result, cap)
                    return result

            if value == 'X':
                # X without variable_source — needs context not yet available
                return 0

            # ── Sum of multiple sources ─────────────────────────────
            if value == 'sum' and step_params:
                sources = step_params.get('sources', [])
                total = 0
                for src in sources:
                    total += self._resolve_value(src, state, player_id)
                return total

            # ── Standard variable map ──────────────────────────────
            var_map = {
                'marker_count_military': player.get_marker_total(MarkerType.MILITARY, state) if player else 0,
                'marker_count_culture': player.get_marker_total(MarkerType.CULTURE, state) if player else 0,
                'marker_count_affair': player.get_marker_total(MarkerType.AFFAIR, state) if player else 0,
                'marker_count_power': player.get_marker_total(MarkerType.POWER, state) if player else 0,
                'hand_size': len(player.hand) if player else 0,
                'prestige': player.prestige if player else 0,
                'contribution': player.contribution if player else 0,
                'history_count': len(player.history_area) if player else 0,
                'control_count': len(state.get_friendly_locations(player_id)) if player else 0,
                # Culture contribution sums
                'confucianism_contribution': player.culture_contributions.get(
                    self._culture_enum('儒学'), 0) if player else 0,
                'taoism_contribution': player.culture_contributions.get(
                    self._culture_enum('玄学'), 0) if player else 0,
                'buddhism_contribution': player.culture_contributions.get(
                    self._culture_enum('佛学'), 0) if player else 0,
            }
            if value in var_map:
                return var_map[value]

            # ── Jin court refugee count ────────────────────────────
            if value == 'jin_court_refugee_count':
                count = 0
                for card in state.jin_court:
                    if card.definition and '流民' in (card.definition.name or ''):
                        count += 1
                return count

            # ── Neutral count in regions ───────────────────────────
            if value == 'neutral_count_in_regions' and step_params:
                region_names = step_params.get('regions', [])
                from models.enums import ControlState
                from rules.area_control import REGION_CONFIG
                count = 0
                for reg, cfg in REGION_CONFIG.items():
                    if reg.value in region_names or any(
                        r in cfg.get('locations', []) for r in region_names):
                        for loc_id in cfg.get('locations', []):
                            loc = state.locations.get(loc_id)
                            if loc and loc.controller in (ControlState.NEUTRAL, ControlState.EMPTY):
                                count += 1
                return count

            # Try numeric conversion last
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        return int(value) if value else 0

    @staticmethod
    def _culture_enum(name: str):
        """Convert culture name to CultureType enum."""
        from models.enums import CultureType
        mapping = {
            '儒学': CultureType.CONFUCIANISM, 'confucianism': CultureType.CONFUCIANISM,
            '玄学': CultureType.TAOISM, 'taoism': CultureType.TAOISM,
            '佛学': CultureType.BUDDHISM, 'buddhism': CultureType.BUDDHISM,
        }
        return mapping.get(name)

    def _can_usurp(self, state: "GameState", player_id: str) -> bool:
        """Check if a Jin player can execute usurp effects."""
        player = state.get_player(player_id)
        if not player:
            return False
        from models.enums import FactionType
        if player.faction != FactionType.JIN:
            return False
        other_prestige = []
        for p in state.get_jin_players():
            if p.player_id != player_id:
                other_prestige.append(p.prestige)
        other_prestige.append(state.sima.prestige)
        return all(player.prestige > op for op in other_prestige)

    # ================================================================
    # Condition system — thin dispatch to CONDITION_REGISTRY
    # ================================================================

    def check_condition(self, condition: "Condition", state: "GameState",
                        player_id: str) -> bool:
        """Public entry point for condition checking.

        Used by both step-level conditions and play_condition checks
        (e.g. _check_event_condition in game.py).
        """
        return self._check_condition(condition, state, player_id)

    def _check_condition(self, condition: "Condition", state: "GameState",
                         player_id: str, context: dict = None) -> bool:
        """Evaluate a condition by dispatching to its registered operator."""
        if condition is None:
            return True

        ct = condition.condition_type
        operator = CONDITION_REGISTRY.get(ct)
        if operator is None:
            # Unknown condition type — assume met rather than blocking
            return True

        return operator.check(condition, state, player_id, context, self)

    # ================================================================
    # Shared utilities for condition operators (called via resolver.*)
    # ================================================================

    def _resolve_compare_value(self, value: Any, state: "GameState",
                               player_id: str) -> int:
        """Resolve a compare left/right operand to a numeric value."""
        if isinstance(value, (int, float)):
            return int(value)
        if not isinstance(value, str):
            return 0

        player = state.get_player(player_id)

        # Player attributes
        attr_map = {
            "military": player.military if player else 0,
            "vp": player.vp if player else 0,
            "prestige": player.prestige if player else 0,
            "contribution": player.contribution if player else 0,
            "order": player.order if player else 0,
            "friend_count": len(player.staff_area) if player else 0,
            "staff_limit": player.staff_limit if player else 0,
            "hand_count": len(player.hand) if player else 0,
            "history_count": len(player.history_area) if player else 0,
            "army_placed_count": player.army_placed_count if player else 0,
            "army_reserve_count": player.army_reserve_count if player else 0,
        }
        if value in attr_map:
            return attr_map[value]

        # Prestige lead
        if value == "prestige_lead" and player:
            others = [p.prestige for p in state.get_jin_players()
                      if p.player_id != player_id]
            return player.prestige - max(others) if others else player.prestige

        # Marker counts
        marker_map = {
            "power_marker_count": "POWER", "military_marker_count": "MILITARY",
            "culture_marker_count": "CULTURE", "affair_marker_count": "AFFAIR",
        }
        if value in marker_map:
            from models.enums import MarkerType
            mt = MarkerType[marker_map[value]]
            return player.get_marker_total(mt, state) if player else 0

        # Culture level: culture_level_confucianism / taoism / buddhism
        if value.startswith("culture_level_"):
            return self._get_culture_level(state, value.replace("culture_level_", ""))

        # Region count: region_count_confucianism / taoism / buddhism
        if value.startswith("region_count_"):
            return self._get_culture_region_count(state, value.replace("region_count_", ""))

        # Fallback
        return self._resolve_value(value, state, player_id)

    def _get_culture_level(self, state: "GameState", culture_name: str) -> int:
        """Get the supply level of a culture track."""
        from models.enums import CultureType
        culture_map = {
            "confucianism": CultureType.CONFUCIANISM, "儒学": CultureType.CONFUCIANISM,
            "taoism": CultureType.TAOISM, "玄学": CultureType.TAOISM,
            "buddhism": CultureType.BUDDHISM, "佛学": CultureType.BUDDHISM,
        }
        ct = culture_map.get(culture_name)
        if ct and ct in state.culture_tracks:
            return state.culture_tracks[ct].supply_level
        return 0

    def _get_culture_region_count(self, state: "GameState",
                                  culture_name: str) -> int:
        """Get the number of map locations with markers of a specific culture."""
        from models.enums import CultureType
        culture_map = {
            "confucianism": CultureType.CONFUCIANISM, "儒学": CultureType.CONFUCIANISM,
            "taoism": CultureType.TAOISM, "玄学": CultureType.TAOISM,
            "buddhism": CultureType.BUDDHISM, "佛学": CultureType.BUDDHISM,
        }
        ct = culture_map.get(culture_name)
        if ct and ct in state.culture_tracks:
            return state.culture_tracks[ct].map_count
        return 0
