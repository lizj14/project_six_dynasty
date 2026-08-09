"""Condition operators — one class per condition_type, Strategy pattern.

Each operator handles a single condition_type. The registry maps condition_type
strings to operator instances, turning EffectResolver._check_condition into a
thin dispatch.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from .effect_ast import Condition

if TYPE_CHECKING:
    from .effect_resolver import EffectResolver


# ============================================================
# Registry
# ============================================================

CONDITION_REGISTRY: dict[str, "ConditionOperator"] = {}


def register_condition(cls):
    """Class decorator: register a condition operator by its condition_type.

    A class may set `aliases: list[str]` for additional names that map to it.
    """
    instance = cls()
    names = [instance.condition_type] + getattr(cls, 'aliases', [])
    for name in names:
        if name:
            CONDITION_REGISTRY[name] = instance
    return cls


# ============================================================
# Base class
# ============================================================

class ConditionOperator(ABC):
    """Abstract base for condition type operators."""
    condition_type: str = ""
    aliases: list[str] = []

    @abstractmethod
    def check(self, condition: Condition, state, player_id: str,
              context: dict, resolver: "EffectResolver") -> bool:
        """Evaluate this condition against the game state."""
        ...

    # ── Shared helpers ────────────────────────────────────────

    def _player(self, state, player_id: str):
        return state.get_player(player_id)

    def _resolve(self, value: Any, state, player_id: str,
                 resolver: "EffectResolver") -> int:
        return resolver._resolve_value(value, state, player_id)

    def _resolve_compare(self, value: Any, state, player_id: str,
                         resolver: "EffectResolver") -> int:
        return resolver._resolve_compare_value(value, state, player_id)

    def _recurse(self, condition: Condition, state, player_id: str,
                 context: dict, resolver: "EffectResolver") -> bool:
        return resolver._check_condition(condition, state, player_id, context)

    def _parse_marker(self, name: str):
        """Convert marker name (Chinese or English) to MarkerType enum."""
        from models.enums import MarkerType
        mapping = {
            "军事": MarkerType.MILITARY, "military": MarkerType.MILITARY,
            "文化": MarkerType.CULTURE, "culture": MarkerType.CULTURE,
            "内政": MarkerType.AFFAIR, "affair": MarkerType.AFFAIR,
            "权谋": MarkerType.POWER, "power": MarkerType.POWER,
        }
        return mapping.get(name)

    def _parse_culture(self, name: str):
        """Convert culture name (Chinese or English) to CultureType enum."""
        from models.enums import CultureType
        mapping = {
            "儒学": CultureType.CONFUCIANISM, "confucianism": CultureType.CONFUCIANISM,
            "玄学": CultureType.TAOISM, "taoism": CultureType.TAOISM,
            "佛学": CultureType.BUDDHISM, "buddhism": CultureType.BUDDHISM,
        }
        return mapping.get(name)


# ============================================================
# Logical combinators
# ============================================================

@register_condition
class AndCondition(ConditionOperator):
    """All sub-conditions must be met."""
    condition_type = "and"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        for cd in condition.params.get("conditions", []):
            sub = Condition(**cd) if isinstance(cd, dict) else cd
            if not self._recurse(sub, state, player_id, context, resolver):
                return False
        return True


@register_condition
class NotCondition(ConditionOperator):
    """Sub-condition must NOT be met."""
    condition_type = "not"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        sub_cd = condition.params.get("condition", {})
        sub = Condition(**sub_cd) if isinstance(sub_cd, dict) else sub_cd
        return not self._recurse(sub, state, player_id, context, resolver)


# ============================================================
# Player identity
# ============================================================

@register_condition
class IsFactionCondition(ConditionOperator):
    """Check if player belongs to a specific faction."""
    condition_type = "is_faction"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        faction = condition.params.get("faction", "")
        player = self._player(state, player_id)
        if not player:
            return False
        from models.enums import FactionType
        if faction in ("north", "北方"):
            return player.faction == FactionType.NORTH
        if faction in ("jin", "东晋", "晋"):
            return player.faction == FactionType.JIN
        return player.faction.value == faction


@register_condition
class CanUsurpCondition(ConditionOperator):
    """Check if a Jin player can execute usurp effects."""
    condition_type = "can_usurp"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        return resolver._can_usurp(state, player_id)


# ============================================================
# Resources
# ============================================================

@register_condition
class CompareCondition(ConditionOperator):
    """Compare two numeric values: left OP right."""
    condition_type = "compare"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        params = condition.params
        left = self._resolve_compare(params.get("left"), state, player_id, resolver)
        right = self._resolve_compare(params.get("right"), state, player_id, resolver)
        op = params.get("op", ">=")

        ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
               "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
               "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
        return ops.get(op, lambda a, b: False)(left, right)


@register_condition
class HasMilitaryCondition(ConditionOperator):
    """Check if player's military >= threshold."""
    condition_type = "has_military"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        return player.military >= condition.params.get("amount", 0)


@register_condition
class StaffHasSpaceCondition(ConditionOperator):
    """Check if player can play another friend card."""
    condition_type = "staff_has_space"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        return player.can_play_friend() if player else False


@register_condition
class HasExpeditionCondition(ConditionOperator):
    """Check if player has expedition marker."""
    condition_type = "has_expedition"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        return player.has_expedition_marker if player else False


# ============================================================
# Markers
# ============================================================

@register_condition
class MarkerCountGtCondition(ConditionOperator):
    """Check if marker count > threshold."""
    condition_type = "marker_count_gt"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        mt = self._parse_marker(condition.params.get("marker", ""))
        threshold = condition.params.get("threshold", 0)
        return player.get_marker_total(mt, state) > threshold if mt else False


@register_condition
class MarkerCountCondition(ConditionOperator):
    """Check if marker count >= min (used in AND combinations)."""
    condition_type = "marker_count"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        mt = self._parse_marker(condition.params.get("marker", ""))
        min_val = condition.params.get("min", 0)
        return player.get_marker_total(mt, state) >= min_val if mt else False


@register_condition
class HasTokenCondition(ConditionOperator):
    """Check if player has a named token (e.g. expedition marker)."""
    condition_type = "has_token"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        token = condition.params.get("token", "")
        return self._resolve(token, state, player_id, resolver) > 0


# ============================================================
# Culture
# ============================================================

@register_condition
class CultureLevelGtCondition(ConditionOperator):
    """Check if culture track supply level > threshold."""
    condition_type = "culture_level_gt"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        ct = self._parse_culture(condition.params.get("culture", ""))
        threshold = condition.params.get("threshold", 0)
        if ct and ct in player.culture_contributions:
            return player.culture_contributions[ct] > threshold
        return False


@register_condition
class CultureContributionGtCondition(ConditionOperator):
    """Check if player's personal contribution to a culture > threshold."""
    condition_type = "culture_contribution_gt"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        ct = self._parse_culture(condition.params.get("culture", ""))
        threshold = condition.params.get("threshold", 0)
        if ct and ct in player.culture_contributions:
            return player.culture_contributions[ct] > threshold
        return False


@register_condition
class CultureMostEmptyCondition(ConditionOperator):
    """Check if player has the lowest sum of culture contributions."""
    condition_type = "culture_most_empty"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        player_sum = sum(player.culture_contributions.values())
        others = [p for p in state.get_all_players()
                  if p.player_id != player_id]
        return all(player_sum <= sum(p.culture_contributions.values())
                   for p in others)


# ============================================================
# Order / Prestige
# ============================================================

@register_condition
class IsLowestOrderCondition(ConditionOperator):
    """Check if player has the lowest order (highest order value)."""
    condition_type = "is_lowest_order"
    aliases = ["order_lowest"]

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        jin = state.get_jin_players()
        if not jin:
            return False
        max_order = max(p.order for p in jin)
        return player.order == max_order


@register_condition
class IsLowestCultureSumCondition(ConditionOperator):
    """Check if player has the lowest total culture contribution sum."""
    condition_type = "is_lowest_culture_sum"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        player_sum = sum(player.culture_contributions.values())
        jin = state.get_jin_players()
        if not jin:
            return False
        min_sum = min(sum(p.culture_contributions.values()) for p in jin)
        return player_sum == min_sum


@register_condition
class PrestigeHighestCondition(ConditionOperator):
    """Check if player has strictly highest prestige among Jin players."""
    condition_type = "prestige_highest"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        jin = state.get_jin_players()
        if not jin:
            return False
        mp = max(p.prestige for p in jin)
        ties = [p for p in jin if p.prestige == mp]
        return len(ties) == 1 and player.prestige == mp


# ============================================================
# Region / Location
# ============================================================

class _RegionCondition(ConditionOperator):
    """Shared base for region-based conditions."""

    def _find_region(self, region_name: str):
        """Resolve a region name (Chinese or enum value) to a Region enum."""
        from models.enums import Region
        from rules.area_control import REGION_CONFIG

        for reg, cfg in REGION_CONFIG.items():
            if reg.value == region_name:
                return reg
            if region_name in cfg.get("locations", []):
                return reg
        for reg in Region:
            if reg.value == region_name:
                return reg
        return None

        for reg, cfg in REGION_CONFIG.items():
            if reg.value == resolved:
                return reg
            if resolved in cfg.get("locations", []):
                return reg
        for reg in Region:
            if reg.value == resolved:
                return reg
        return None


@register_condition
class ControlRegionCondition(_RegionCondition):
    """Check if player controls a region (partial control, rulebook §3.2).

    "控制" = partial control: player occupies more than threshold locations.
    This is distinct from "完全控制" (full control = all locations).
    """
    condition_type = "control_region"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        region = self._find_region(condition.params.get("region", ""))
        if region is None:
            return False
        from rules.area_control import check_region_control
        result = check_region_control(state, region)
        # Partial control: player has > threshold locations (rulebook §3.2)
        return result.partial_controller == player_id


@register_condition
class FriendlyControlRegionCondition(_RegionCondition):
    """Check if player's faction controls a region (partial or full)."""
    condition_type = "friendly_control_region"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        region = self._find_region(condition.params.get("region", ""))
        if region is None:
            return False
        from rules.area_control import check_region_control
        from models.enums import FactionType
        result = check_region_control(state, region)
        ctrl = result.full_controller or result.partial_controller
        player = self._player(state, player_id)
        if not player:
            return False
        if player.faction == FactionType.NORTH:
            return ctrl == "north"
        # Jin players: own faction OR Sima (allied) control counts as friendly
        return bool(ctrl and (ctrl.startswith("jin") or ctrl == "sima"))


@register_condition
class OccupyLocationCondition(ConditionOperator):
    """Check if player personally occupies a specific location.

    Uses get_own_locations() — only locations where the controller IS
    this player's ControlState, not faction-friendly allies like Sima.
    """
    condition_type = "occupy_location"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        loc = condition.params.get("location", "")
        return loc in state.get_own_locations(player_id)


@register_condition
class OccupyLocationInRegionCondition(ConditionOperator):
    """Check if player personally occupies any location in a region."""
    condition_type = "occupy_location_in_region"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        region_name = condition.params.get("region", "")
        own = state.get_own_locations(player_id)
        from rules.area_control import REGION_CONFIG
        for reg, cfg in REGION_CONFIG.items():
            if reg.value == region_name or region_name in cfg.get("locations", []):
                return any(loc in cfg.get("locations", []) for loc in own)
        return False


# ============================================================
# Route
# ============================================================

@register_condition
class HasRouteCondition(ConditionOperator):
    """Check if there's a BFS path through faction-controlled locations."""
    condition_type = "has_route"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        params = condition.params
        from_loc = params.get("from", "")
        to_loc = params.get("to", "")
        controller = params.get("controller", "jin")

        if from_loc not in state.locations or to_loc not in state.locations:
            return False

        visited = {from_loc}
        queue = [from_loc]

        while queue:
            cur = queue.pop(0)
            if cur == to_loc:
                return True
            for nb in state.get_adjacent_locations(cur):
                if nb in visited:
                    continue
                loc = state.locations.get(nb)
                if not loc:
                    continue
                ctrl = loc.controller.value if hasattr(loc.controller, 'value') else str(loc.controller)
                if controller == "jin":
                    if ctrl in ("jin_p1", "jin_p2", "jin_p3",
                                "jin_1", "jin_2", "jin_3"):
                        visited.add(nb)
                        queue.append(nb)
                elif ctrl == controller:
                    visited.add(nb)
                    queue.append(nb)

        return False


# ============================================================
# Turn tracking
# ============================================================

@register_condition
class OnActionThisTurnCondition(ConditionOperator):
    """Check if player performed a specific action this turn."""
    condition_type = "on_action_this_turn"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        action = condition.params.get("action", "")
        flags = {
            "march": getattr(player, 'has_marched', False),
            "occupy": getattr(player, 'has_occupied', False),
            "fortify": getattr(player, 'has_fortified_quick', False),
            "convert": getattr(player, 'has_converted', False),
        }
        return flags.get(action, False)


# ============================================================
# Cards / Archive / Goals
# ============================================================

@register_condition
class ArchiveCountGeCondition(ConditionOperator):
    """Check if player's history area has >= N cards."""
    condition_type = "archive_count_ge"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        return len(player.history_area) >= condition.params.get("count", 0)


@register_condition
class NotCompletedGoalCondition(ConditionOperator):
    """Check if player has not yet completed a specific goal."""
    condition_type = "not_completed_goal"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        player = self._player(state, player_id)
        if not player:
            return False
        goal = condition.params.get("goal_name", "")
        goal_cards = getattr(player, 'goal_cards', [])
        return goal not in goal_cards


# ============================================================
# Fallback
# ============================================================

@register_condition
class RawTextCondition(ConditionOperator):
    """Unparseable condition — assume met rather than blocking."""
    condition_type = "raw_text"

    def check(self, condition, state, player_id, context, resolver) -> bool:
        return True
