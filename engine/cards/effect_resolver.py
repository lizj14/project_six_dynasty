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

    # ================================================================
    # Public API
    # ================================================================

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
                for _ in range(count):
                    if player and player.hand:
                        state.main_discard.append(player.hand.pop())
                        result.events.append({"type": "pay_discard"})
            elif cost.cost_type == "pay_military":
                amount = cost.params.get("amount", 0)
                if player:
                    player.military = max(0, player.military - amount)
                    result.events.append({"type": "pay_military", "amount": amount})
            elif cost.cost_type == "pay_vp":
                amount = cost.params.get("amount", 0)
                if player:
                    player.vp = max(0, player.vp - amount)
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

        return result

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

        return operator.execute(step, state, player_id, context, self)

    # ================================================================
    # Shared utilities (used by operators via resolver.*)
    # ================================================================

    def _resolve_value(self, value: Any, state: "GameState", player_id: str) -> int:
        """Resolve a value that might be a variable or literal number."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            player = state.get_player(player_id)
            # Variable lookups (Phase 2c will expand this)
            from models.enums import MarkerType
            var_map = {
                'X': 0,
                'marker_count_military': player.get_marker(MarkerType.MILITARY) if player else 0,
                'marker_count_culture': player.get_marker(MarkerType.CULTURE) if player else 0,
                'marker_count_affair': player.get_marker(MarkerType.AFFAIR) if player else 0,
                'marker_count_power': player.get_marker(MarkerType.POWER) if player else 0,
                'hand_size': len(player.hand) if player else 0,
                'prestige': player.prestige if player else 0,
                'contribution': player.contribution if player else 0,
                'history_count': len(player.history_area) if player else 0,
                'control_count': len(state.get_friendly_locations(player_id)) if player else 0,
            }
            if value in var_map:
                return var_map[value]
            # Try numeric conversion last
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        return int(value) if value else 0

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
    # Condition system
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
        """Evaluate a condition against the current game state.

        Supports all condition types used in card JSONs plus logical
        combinators (and, not) that recurse into sub-conditions.
        """
        if condition is None:
            return True

        ct = condition.condition_type
        params = condition.params or {}
        player = state.get_player(player_id)

        # ── Logical combinators ──────────────────────────────────

        if ct == "and":
            sub_conds = params.get("conditions", [])
            for cd in sub_conds:
                sub = Condition(**cd) if isinstance(cd, dict) else cd
                if not self._check_condition(sub, state, player_id, context):
                    return False
            return True

        if ct == "not":
            sub_cd = params.get("condition", {})
            sub = Condition(**sub_cd) if isinstance(sub_cd, dict) else sub_cd
            return not self._check_condition(sub, state, player_id, context)

        # ── Player identity ──────────────────────────────────────

        if ct == "is_faction":
            faction = params.get("faction", "")
            if not player:
                return False
            from models.enums import FactionType
            if faction in ("north", "北方"):
                return player.faction == FactionType.NORTH
            if faction in ("jin", "东晋", "晋"):
                return player.faction == FactionType.JIN
            return player.faction.value == faction

        if ct == "can_usurp":
            return self._can_usurp(state, player_id)

        # ── Resource comparisons ─────────────────────────────────

        if ct == "compare":
            return self._eval_compare(params, state, player_id)

        if ct == "has_military":
            if not player:
                return False
            return player.military >= params.get("amount", 0)

        if ct == "staff_has_space":
            if not player:
                return False
            return player.can_play_friend()

        if ct == "has_expedition":
            if not player:
                return False
            return player.has_expedition_marker

        # ── Markers ──────────────────────────────────────────────

        if ct == "marker_count_gt":
            return self._check_marker_count(player, params, "gt")

        if ct == "marker_count":
            return self._check_marker_count(player, params, "ge")

        if ct == "has_token":
            token = params.get("token", "")
            if not player:
                return False
            return self._resolve_value(token, state, player_id) > 0

        # ── Culture ──────────────────────────────────────────────

        if ct == "culture_level_gt":
            return self._check_culture_level(state, player, params)

        if ct == "culture_contribution_gt":
            return self._check_culture_contribution(player, params)

        if ct == "culture_most_empty":
            return self._check_culture_most_empty(state, player)

        # ── Order / Prestige ─────────────────────────────────────

        if ct == "is_lowest_order" or ct == "order_lowest":
            return self._check_lowest_order(state, player)

        if ct == "is_lowest_culture_sum":
            return self._check_lowest_culture_sum(state, player)

        if ct == "prestige_highest":
            return self._check_prestige_highest(state, player)

        # ── Region / Location ────────────────────────────────────

        if ct == "control_region":
            return self._check_control_region(state, player_id, params,
                                              require_full=True)

        if ct == "friendly_control_region":
            return self._check_control_region(state, player_id, params,
                                              require_full=False)

        if ct == "occupy_location":
            loc_name = params.get("location", "")
            friendly = state.get_friendly_locations(player_id)
            return loc_name in friendly

        if ct == "occupy_location_in_region":
            region_name = params.get("region", "")
            friendly = state.get_friendly_locations(player_id)
            from rules.area_control import REGION_CONFIG
            for reg, cfg in REGION_CONFIG.items():
                if reg.value == region_name or region_name in cfg.get("locations", []):
                    region_locs = cfg.get("locations", [])
                    return any(loc in region_locs for loc in friendly)
            return False

        # ── Route ────────────────────────────────────────────────

        if ct == "has_route":
            return self._check_has_route(state, params)

        # ── Turn tracking ────────────────────────────────────────

        if ct == "on_action_this_turn":
            return self._check_action_this_turn(state, player, params)

        # ── Cards / Archive ──────────────────────────────────────

        if ct == "archive_count_ge":
            if not player:
                return False
            return len(player.history_area) >= params.get("count", 0)

        # ── Goals ────────────────────────────────────────────────

        if ct == "not_completed_goal":
            if not player:
                return False
            goal_name = params.get("goal_name", "")
            return goal_name not in player.goal_cards

        # ── Fallback ─────────────────────────────────────────────

        if ct == "raw_text":
            # Unparseable condition — assume met rather than blocking
            return True

        # Unknown condition type — log and assume met
        return True

    # ── Condition helpers ────────────────────────────────────────

    def _eval_compare(self, params: dict, state: "GameState",
                      player_id: str) -> bool:
        """Evaluate a 'compare' condition with left/op/right."""
        left = self._resolve_compare_value(params.get("left"), state, player_id)
        right = self._resolve_compare_value(params.get("right"), state, player_id)
        op = params.get("op", ">=")

        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        return False

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

        # Prestige lead (player prestige minus max of other Jin players)
        if value == "prestige_lead" and player:
            others = [p.prestige for p in state.get_jin_players()
                      if p.player_id != player_id]
            return player.prestige - max(others) if others else player.prestige

        # Marker counts
        marker_map = {
            "power_marker_count": "POWER",
            "military_marker_count": "MILITARY",
            "culture_marker_count": "CULTURE",
            "affair_marker_count": "AFFAIR",
        }
        if value in marker_map:
            from models.enums import MarkerType
            mt = MarkerType[marker_map[value]]
            return player.get_marker(mt) if player else 0

        # Culture level: culture_level_confucianism / taoism / buddhism
        if value.startswith("culture_level_"):
            culture_name = value.replace("culture_level_", "")
            return self._get_culture_level(state, culture_name)

        # Region count: region_count_confucianism / taoism / buddhism
        if value.startswith("region_count_"):
            culture_name = value.replace("region_count_", "")
            return self._get_culture_region_count(state, culture_name)

        # Fallback: try _resolve_value for variable strings, then numeric
        return self._resolve_value(value, state, player_id)

    def _check_marker_count(self, player: "PlayerState", params: dict,
                            mode: str) -> bool:
        """Check marker count > threshold (gt) or >= min (ge)."""
        if not player:
            return False
        marker_name = params.get("marker", "")
        if mode == "gt":
            threshold = params.get("threshold", 0)
        else:
            threshold = params.get("min", 0)

        # Marker name can be Chinese or English
        from models.enums import MarkerType
        marker_enum = {
            "军事": MarkerType.MILITARY, "military": MarkerType.MILITARY,
            "文化": MarkerType.CULTURE, "culture": MarkerType.CULTURE,
            "内政": MarkerType.AFFAIR, "affair": MarkerType.AFFAIR,
            "权谋": MarkerType.POWER, "power": MarkerType.POWER,
        }
        mt = marker_enum.get(marker_name)
        if mt:
            return player.get_marker(mt) > threshold if mode == "gt" else player.get_marker(mt) >= threshold
        return False

    def _check_culture_level(self, state: "GameState", player: "PlayerState",
                             params: dict) -> bool:
        """Check if a player's culture contribution level exceeds threshold."""
        if not player:
            return False
        culture_name = params.get("culture", "")
        threshold = params.get("threshold", 0)
        from models.enums import CultureType
        culture_map = {
            "儒学": CultureType.CONFUCIANISM, "confucianism": CultureType.CONFUCIANISM,
            "玄学": CultureType.TAOISM, "taoism": CultureType.TAOISM,
            "佛学": CultureType.BUDDHISM, "buddhism": CultureType.BUDDHISM,
        }
        ct = culture_map.get(culture_name)
        if ct and ct in player.culture_contributions:
            return player.culture_contributions[ct] > threshold
        return False

    def _check_culture_contribution(self, player: "PlayerState",
                                    params: dict) -> bool:
        """Check if player's personal contribution to a culture exceeds threshold."""
        if not player:
            return False
        culture_name = params.get("culture", "")
        threshold = params.get("threshold", 0)
        from models.enums import CultureType
        culture_map = {
            "儒学": CultureType.CONFUCIANISM, "confucianism": CultureType.CONFUCIANISM,
            "玄学": CultureType.TAOISM, "taoism": CultureType.TAOISM,
            "佛学": CultureType.BUDDHISM, "buddhism": CultureType.BUDDHISM,
        }
        ct = culture_map.get(culture_name)
        if ct and ct in player.culture_contributions:
            return player.culture_contributions[ct] > threshold
        return False

    def _check_culture_most_empty(self, state: "GameState",
                                  player: "PlayerState") -> bool:
        """Check if player has the most empty slots across culture tracks.

        'Empty' means lowest contribution level — the culture where the player
        has room to grow. Returns True if this player has strictly the lowest
        sum of culture contributions among all players.
        """
        if not player:
            return False
        player_sum = sum(player.culture_contributions.values())
        all_players = state.get_all_players()
        if not all_players:
            return False
        other_sums = [
            sum(p.culture_contributions.values())
            for p in all_players if p.player_id != player.player_id
        ]
        return all(player_sum <= s for s in other_sums)

    def _check_lowest_order(self, state: "GameState",
                            player: "PlayerState") -> bool:
        """Check if player has the lowest order (highest order value)."""
        if not player:
            return False
        jin_players = state.get_jin_players()
        if not jin_players:
            return False
        max_order = max(p.order for p in jin_players)
        return player.order == max_order

    def _check_lowest_culture_sum(self, state: "GameState",
                                  player: "PlayerState") -> bool:
        """Check if player has the lowest total culture contribution sum."""
        if not player:
            return False
        player_sum = sum(player.culture_contributions.values())
        jin_players = state.get_jin_players()
        if not jin_players:
            return False
        min_sum = min(sum(p.culture_contributions.values()) for p in jin_players)
        return player_sum == min_sum

    def _check_prestige_highest(self, state: "GameState",
                                player: "PlayerState") -> bool:
        """Check if player has the strictly highest prestige among Jin players."""
        if not player:
            return False
        jin_players = state.get_jin_players()
        if not jin_players:
            return False
        max_prestige = max(p.prestige for p in jin_players)
        # Must be strictly highest (no tie)
        ties = [p for p in jin_players if p.prestige == max_prestige]
        return len(ties) == 1 and player.prestige == max_prestige

    def _check_control_region(self, state: "GameState", player_id: str,
                              params: dict, require_full: bool) -> bool:
        """Check region control: full_controller (require_full=True)
        or friendly (any Jin controls or North controls).

        Region name can be Chinese (e.g. "巴蜀") or English enum value.
        """
        region_name = params.get("region", "")
        from models.enums import Region
        from rules.area_control import check_region_control, REGION_CONFIG

        # Resolve region name to Region enum
        target_region = None
        for reg, cfg in REGION_CONFIG.items():
            if reg.value == region_name:
                target_region = reg
                break
            if region_name in cfg.get("locations", []):
                target_region = reg
                break

        if target_region is None:
            # Try matching by Region enum value
            for reg in Region:
                if reg.value == region_name:
                    target_region = reg
                    break

        if target_region is None:
            return False

        result = check_region_control(state, target_region)

        if require_full:
            # "控制" → must be the full controller
            return result.full_controller == player_id
        else:
            # "友方控制" → friendly faction controls
            player = state.get_player(player_id)
            if not player:
                return False
            from models.enums import FactionType
            ctrl = result.full_controller or result.partial_controller
            if player.faction == FactionType.NORTH:
                return ctrl == "north"
            else:
                return ctrl and ctrl.startswith("jin")

    def _check_has_route(self, state: "GameState", params: dict) -> bool:
        """Check if there is a path from one location to another where all
        intermediate locations are controlled by a specific faction.

        Uses BFS restricted to locations controlled by the target faction.
        """
        from_loc = params.get("from", "")
        to_loc = params.get("to", "")
        controller = params.get("controller", "jin")

        if from_loc not in state.locations or to_loc not in state.locations:
            return False

        # BFS through locations controlled by the specified faction
        visited = set()
        queue = [from_loc]
        visited.add(from_loc)

        while queue:
            current = queue.pop(0)
            if current == to_loc:
                return True

            for neighbor in state.get_adjacent_locations(current):
                if neighbor in visited:
                    continue
                loc = state.locations.get(neighbor)
                if not loc:
                    continue
                # Check if location is controlled by the required faction
                ctrl = loc.controller.value if hasattr(loc.controller, 'value') else str(loc.controller)
                if controller == "jin":
                    if ctrl in ("jin_p1", "jin_p2", "jin_p3", "jin_1", "jin_2", "jin_3"):
                        visited.add(neighbor)
                        queue.append(neighbor)
                elif ctrl == controller:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    def _check_action_this_turn(self, state: "GameState",
                                player: "PlayerState", params: dict) -> bool:
        """Check if the player has performed a specific action this turn."""
        if not player:
            return False
        action = params.get("action", "")
        action_flags = {
            "march": getattr(player, 'has_marched', False),
            "occupy": getattr(player, 'has_occupied', False),
            "fortify": getattr(player, 'has_fortified_quick', False),
            "convert": getattr(player, 'has_converted', False),
        }
        return action_flags.get(action, False)

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
