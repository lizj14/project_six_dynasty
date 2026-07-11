"""Effect operators — one class per effect_type, Strategy pattern.

Each operator handles a single effect_type. The registry maps effect_type strings
to operator instances, turning EffectResolver._execute_step into a thin dispatch.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from .effect_ast import EffectStep, EffectType
from models.enums import ControlState

if TYPE_CHECKING:
    from .effect_resolver import EffectResolver, ResolveResult


# ============================================================
# Registry
# ============================================================

OPERATOR_REGISTRY: dict[str, "EffectOperator"] = {}


def register(cls):
    """Class decorator: register an operator by its effect_type."""
    instance = cls()
    OPERATOR_REGISTRY[instance.effect_type] = instance
    return cls


# ============================================================
# Base class
# ============================================================

class EffectOperator(ABC):
    """Abstract base for effect type operators."""
    effect_type: str = ""

    @abstractmethod
    def execute(self, step: EffectStep, state, player_id: str,
                context: dict, resolver: "EffectResolver") -> "ResolveResult":
        """Execute this effect step against the game state."""
        ...

    def _resolve(self, value: Any, state, player_id: str, resolver: "EffectResolver",
                 step_params: dict = None) -> int:
        """Delegate to resolver's value resolution, passing step params for X/sum."""
        return resolver._resolve_value(value, state, player_id, step_params)


# ============================================================
# Resource operators (player stats)
# ============================================================

@register
class GainMilitaryOperator(EffectOperator):
    effect_type = EffectType.GAIN_MILITARY

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = self._resolve(step.params.get("amount", 0), state, player_id, resolver, step.params)
        if player:
            player.military += amount
            result.events.append({"type": "gain_military", "amount": amount})
        return result


@register
class GainVPOperator(EffectOperator):
    effect_type = EffectType.GAIN_VP

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = self._resolve(step.params.get("amount", 0), state, player_id, resolver, step.params)
        if player:
            player.vp += amount
            result.events.append({"type": "gain_vp", "amount": amount})
            state.check_vp_game_end(player_id)
            resolver._fire_trigger("on_gain_vp", player_id,
                                   {"amount": amount})
        return result


@register
class LoseVPOperator(EffectOperator):
    effect_type = EffectType.LOSE_VP

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = self._resolve(step.params.get("amount", 0), state, player_id, resolver, step.params)
        if player:
            player.vp = max(0, player.vp - amount)
            result.events.append({"type": "lose_vp", "amount": amount})
        return result


@register
class LoseMilitaryOperator(EffectOperator):
    effect_type = EffectType.LOSE_MILITARY

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = self._resolve(step.params.get("amount", 0), state, player_id, resolver, step.params)
        if player:
            lost = min(player.military, amount)
            player.military -= lost
            result.events.append({"type": "lose_military", "amount": lost})
        return result


@register
class PayMilitaryOperator(EffectOperator):
    effect_type = EffectType.PAY_MILITARY

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 0)
        if player:
            player.military = max(0, player.military - amount)
            result.events.append({"type": "pay_military", "amount": amount})
        return result


@register
class PayVPOperator(EffectOperator):
    effect_type = EffectType.PAY_VP

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 0)
        if player:
            player.vp = max(0, player.vp - amount)
            result.events.append({"type": "pay_vp", "amount": amount})
        return result


# ============================================================
# Card operators (deck / hand / court / archive)
# ============================================================

@register
class DrawCardsOperator(EffectOperator):
    effect_type = EffectType.DRAW_CARDS

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        count = step.params.get("count", 1)
        draw_events = state.draw_cards(player_id, count)
        result.events.extend(draw_events)
        return result


@register
class DiscardCardsOperator(EffectOperator):
    effect_type = EffectType.DISCARD_CARDS

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        count = step.params.get("count", 1)
        for _ in range(count):
            if player and player.hand:
                state.main_discard.append(player.hand.pop())
                result.events.append({"type": "discard"})
                resolver._fire_trigger("on_discard", player_id)
        return result


@register
class ArchiveThisOperator(EffectOperator):
    effect_type = EffectType.ARCHIVE_THIS

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Card archives itself — handled by the caller via card reference
        result.events.append({"type": "archive_this"})
        return result


@register
class ArchiveCardOperator(EffectOperator):
    effect_type = EffectType.ARCHIVE_CARD

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        count = step.params.get("count", 1)
        for _ in range(count):
            if player and player.hand:
                card = player.hand.pop()
                player.history_area.append(card)
                player.vp += card.definition.history_vp
                result.events.append({"type": "archive_card", "card": card.name})
                resolver._fire_trigger("on_archive", player_id,
                                       {"card": card})
                from models.enums import FactionType
                if player.faction == FactionType.JIN:
                    player.contribution = min(9, player.contribution + 1)
        return result


@register
class ArchiveCourtOperator(EffectOperator):
    effect_type = EffectType.ARCHIVE_COURT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Remove a card from court to discard
        court = state.get_court_cards(player_id)
        count = step.params.get("count", 1)
        for _ in range(count):
            if court:
                card = court.pop()
                state.main_discard.append(card)
                result.events.append({"type": "archive_court", "card": card.name})
        return result


@register
class PlayCardOperator(EffectOperator):
    effect_type = EffectType.PLAY_CARD

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        count = step.params.get("count", 1)
        filter_spec = step.params.get("filter")  # e.g. {"marker": "military"} or {"exclude_marker": "military"}
        for i in range(count):
            card_ids = context.get("play_card_ids", []) if context else []
            card_id = card_ids[i] if i < len(card_ids) else step.params.get("card_id")
            if card_id and player:
                # Find and play the card from hand
                for j, c in enumerate(player.hand):
                    if c.definition.card_id == card_id:
                        played = player.hand.pop(j)
                        # Delegate to resolver's action_system for PlayCardAction
                        if resolver.action_system:
                            from engine.actions.card_actions import PlayCardAction
                            action = PlayCardAction(player_id=player_id, card=played)
                            r = resolver.action_system.execute(state, action)
                            result.events.extend(r.events if r.success else [])
                            if not r.success:
                                if not r.success: result.errors.append(r.error or "action failed")
                        break
            else:
                result.events.append({
                    "type": "play_card_requested", "count": count,
                    "filter": filter_spec, "index": i,
                })
        return result


@register
class SearchOperator(EffectOperator):
    effect_type = EffectType.SEARCH

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        if resolver.action_system:
            from engine.actions.special_actions import SearchAction
            p = step.params
            action = SearchAction(
                player_id=player_id,
                search_count=p.get("count", 1),
                search_type=p.get("search_type", ""),
            )
            r = resolver.action_system.execute(state, action)
            result.events.extend(r.events if r.success else [])
        return result


@register
class DraftOperator(EffectOperator):
    effect_type = EffectType.DRAFT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        if resolver.action_system:
            from engine.actions.special_actions import LevyAction
            p = step.params
            count = p.get("count", 1)
            filter_spec = p.get("filter")
            for i in range(count):
                card_ids = context.get("draft_card_ids", []) if context else []
                card_id = card_ids[i] if i < len(card_ids) else p.get("card_id")
                if card_id:
                    action = LevyAction(player_id=player_id, card_id=card_id)
                    r = resolver.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])
                    if not r.success:
                        if not r.success: result.errors.append(r.error or "action failed")
                else:
                    result.events.append({
                        "type": "draft_requested",
                        "count": count, "filter": filter_spec, "index": i,
                    })
        return result


@register
class SupplyCourtOperator(EffectOperator):
    effect_type = EffectType.SUPPLY_COURT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        count = step.params.get("count", 1)
        deck = state.get_national_deck(player_id)
        court = state.get_court_cards(player_id)
        for _ in range(count):
            if deck:
                court.append(deck.pop(0))
        result.events.append({"type": "supply_court", "count": count})
        return result


# ============================================================
# Map operators (location actions via action_system)
# ============================================================

class _TargetedMapOperator(EffectOperator, ABC):
    """Base for operators that need target selection (march, occupy, fortify)."""

    action_class = None         # e.g. MarchAction
    event_type: str = ""        # e.g. "march_requested"
    context_key: str = ""       # e.g. "march_targets"

    @abstractmethod
    def _get_valid_targets(self, state, player_id: str, step: EffectStep) -> list[str]:
        """Enumerate valid target location IDs for this effect step.

        Subclasses implement the specific filtering logic (march targets,
        occupy targets, etc.).
        """
        ...

    def _select_target(self, step, state, player_id, context, resolver,
                       index: int, extra_info: dict = None) -> Optional[str]:
        """Try to get a target: context → hardcoded → callback → None."""
        from .effect_resolver import ResolveResult

        p = step.params
        # 1. From context (pre-filled by caller)
        targets = context.get(self.context_key, []) if context else []
        if index < len(targets):
            return targets[index]

        # 2. Hardcoded in card data
        if p.get("target_location"):
            return p.get("target_location")

        # 3. Ask agent via callback
        valid = self._get_valid_targets(state, player_id, step)
        if valid and resolver.select_target_callback:
            prompt = {
                "type": self.event_type,
                "options": valid,
            }
            if extra_info:
                prompt.update(extra_info)
            return resolver.select_target_callback(player_id, prompt)

        return None

    def _execute_action(self, state, player_id, target, step, resolver,
                        free=False):
        """Create and execute the map action. Override for special handling."""
        from .effect_resolver import ResolveResult
        action = self.action_class(
            player_id=player_id,
            target_location=target,
        )
        return resolver.action_system.execute(state, action)


@register
class MarchOperator(_TargetedMapOperator):
    effect_type = EffectType.MARCH
    event_type = "march_requested"
    context_key = "march_targets"

    def _get_valid_targets(self, state, player_id, step):
        """Enemy or neutral locations adjacent to friendly."""
        friendly = state.get_friendly_locations(player_id)
        player_cs = state._player_control_state(player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            if loc.is_friendly_to(player_cs):
                continue
            neighbors = state.get_adjacent_locations(loc_id)
            if any(n in friendly for n in neighbors):
                valid.append(loc_id)
        return valid

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.quick_actions import MarchAction
        result = ResolveResult()
        if not resolver.action_system:
            return result

        p = step.params
        count = p.get("count", 1)
        free = p.get("free", False)
        cost_reduction = p.get("cost_reduction", 0)

        for i in range(count):
            target = self._select_target(step, state, player_id, context,
                                         resolver, i,
                                         extra_info={"free": free,
                                                     "cost_reduction": cost_reduction})
            if target:
                action = MarchAction(
                    player_id=player_id,
                    target_location=target,
                    source_location=p.get("source_location"),
                )
                # Handle free / cost_reduction — temporarily grant military
                player = state.get_player(player_id)
                if free or cost_reduction:
                    cost = action._calculate_cost(state)
                    reduction = cost if free else min(cost_reduction, cost - 1)
                    if reduction > 0 and player:
                        player.military += reduction
                        r = resolver.action_system.execute(state, action)
                        # action.execute() deducts full cost; refund unapplied reduction
                        net_cost = cost - reduction
                        actual_cost = cost  # action already deducted full cost
                        refund = actual_cost - net_cost
                        if refund > 0 and player:
                            player.military += refund
                        result.events.extend(r.events if r.success else [])
                        if not r.success:
                            if not r.success: result.errors.append(r.error or "action failed")
                        continue
                r = resolver.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])
                if not r.success:
                    if not r.success: result.errors.append(r.error or "action failed")
            else:
                result.events.append({
                    "type": "march_requested", "free": free,
                    "cost_reduction": cost_reduction, "index": i,
                    "skipped": True, "reason": "no_target",
                })
        return result


@register
class OccupyOperator(_TargetedMapOperator):
    effect_type = EffectType.OCCUPY
    event_type = "occupy_requested"
    context_key = "occupy_targets"

    def _get_valid_targets(self, state, player_id, step):
        """Empty/neutral locations adjacent to friendly."""
        friendly = state.get_friendly_locations(player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            if loc.controller != ControlState.EMPTY:
                continue
            neighbors = state.get_adjacent_locations(loc_id)
            if any(n in friendly for n in neighbors):
                valid.append(loc_id)
        return valid

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.quick_actions import OccupyAction
        self.action_class = OccupyAction
        result = ResolveResult()
        if not resolver.action_system:
            return result

        p = step.params
        count = p.get("count", 1)
        free = p.get("free", False)

        for i in range(count):
            target = self._select_target(step, state, player_id, context,
                                         resolver, i)
            if target:
                action = OccupyAction(player_id=player_id, target_location=target)
                player = state.get_player(player_id)
                if free and player:
                    player.military += 1  # Grant 1 military temporarily
                    r = resolver.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])
                    if not r.success:
                        if not r.success: result.errors.append(r.error or "action failed")
                else:
                    r = resolver.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])
                    if not r.success:
                        if not r.success: result.errors.append(r.error or "action failed")
            else:
                result.events.append({
                    "type": "occupy_requested", "free": free, "index": i,
                    "skipped": True, "reason": "no_target",
                })
        return result


@register
class FortifyOperator(_TargetedMapOperator):
    effect_type = EffectType.FORTIFY
    event_type = "fortify_requested"
    context_key = "fortify_targets"

    def _get_valid_targets(self, state, player_id, step):
        """Friendly locations that are not fortified."""
        friendly = state.get_friendly_locations(player_id)
        valid = []
        for loc_id in friendly:
            loc = state.locations.get(loc_id)
            if loc and not loc.is_fortified:
                valid.append(loc_id)
        return valid

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.quick_actions import FortifyAction
        self.action_class = FortifyAction
        result = ResolveResult()
        if not resolver.action_system:
            return result

        p = step.params
        count = p.get("count", 1)
        free = p.get("free", False)

        for i in range(count):
            target = self._select_target(step, state, player_id, context,
                                         resolver, i)
            if target:
                action = FortifyAction(player_id=player_id, target_location=target)
                player = state.get_player(player_id)
                if free and player:
                    player.military += 1  # Grant 1 military temporarily
                    r = resolver.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])
                    if not r.success:
                        if not r.success: result.errors.append(r.error or "action failed")
                else:
                    r = resolver.action_system.execute(state, action)
                    result.events.extend(r.events if r.success else [])
                    if not r.success:
                        if not r.success: result.errors.append(r.error or "action failed")
            else:
                result.events.append({
                    "type": "fortify_requested", "free": free, "index": i,
                    "skipped": True, "reason": "no_target",
                })
        return result


@register
class ConvertOperator(EffectOperator):
    effect_type = EffectType.CONVERT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.special_actions import ConvertAction
        result = ResolveResult()
        if not resolver.action_system:
            return result

        p = step.params
        locs = p.get("specific_locations", [])
        restriction = p.get("restriction", [])
        neutral_only = ('neutral' in restriction)
        filter_spec = p.get("filter")

        # 1. Hardcoded locations — execute directly
        if locs:
            count = p.get("count", len(locs))
            for loc_id in locs[:count]:
                action = ConvertAction(
                    player_id=player_id,
                    target_location=loc_id,
                    neutral_only=neutral_only,
                )
                r = resolver.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])
                if not r.success:
                    if not r.success: result.errors.append(r.error or "action failed")
            return result

        # 2. Filter-based — enumerate valid targets and ask agent
        if filter_spec:
            valid = self._get_filtered_locations(state, player_id, filter_spec,
                                                  neutral_only)
            if valid:
                count = p.get("count", 1)
                for i in range(count):
                    target = self._pick_target(
                        state, player_id, resolver, valid, "convert_requested",
                        {"neutral_only": neutral_only})
                    if target:
                        action = ConvertAction(
                            player_id=player_id,
                            target_location=target,
                            neutral_only=neutral_only,
                        )
                        r = resolver.action_system.execute(state, action)
                        result.events.extend(r.events if r.success else [])
                        if not r.success:
                            if not r.success: result.errors.append(r.error or "action failed")
                    else:
                        result.events.append({
                            "type": "convert_requested", "index": i,
                            "skipped": True, "reason": "no_target",
                        })
            else:
                result.events.append({
                    "type": "convert_requested",
                    "skipped": True, "reason": "no_valid_targets",
                })
            return result

        # 3. Neither specific_locations nor filter — fallback
        result.events.append({
            "type": "convert_requested",
            "skipped": True, "reason": "no_target_spec",
        })
        return result

    def _get_filtered_locations(self, state, player_id, filter_spec, neutral_only):
        """Enumerate locations matching a filter dict.

        Supported keys:
          - adjacent: true → must be adjacent to friendly
          - controller: "neutral" | "enemy" | "sima" | "north" | "jin"
          - fortified: true/false
          - region: str → in specified region
          - not_controller: str → exclude a controller
        """
        valid = []
        friendly = state.get_friendly_locations(player_id)
        player_cs = state._player_control_state(player_id)

        for loc_id, loc in state.locations.items():
            # Adjacent filter
            if filter_spec.get("adjacent"):
                neighbors = state.get_adjacent_locations(loc_id)
                if not any(n in friendly for n in neighbors):
                    continue

            # Controller filter
            want_controller = filter_spec.get("controller")
            if want_controller:
                if want_controller == "neutral":
                    if loc.controller not in (ControlState.NEUTRAL, ControlState.EMPTY):
                        continue
                elif want_controller == "enemy":
                    if loc.is_friendly_to(player_cs):
                        continue
                elif want_controller == "sima":
                    if loc.controller != ControlState.SIMA:
                        continue
                elif want_controller == "north":
                    if loc.controller != ControlState.NORTH:
                        continue
                elif want_controller == "jin":
                    jin_states = {ControlState.JIN_P1, ControlState.JIN_P2,
                                  ControlState.JIN_P3}
                    if loc.controller not in jin_states:
                        continue

            # Exclude controller
            not_ctrl = filter_spec.get("not_controller")
            if not_ctrl:
                if not_ctrl == "neutral":
                    if loc.controller in (ControlState.NEUTRAL, ControlState.EMPTY):
                        continue

            # Fortified filter
            if "fortified" in filter_spec:
                if filter_spec["fortified"] and not loc.is_fortified:
                    continue
                if not filter_spec["fortified"] and loc.is_fortified:
                    continue

            # Region filter
            want_region = filter_spec.get("region")
            if want_region:
                from rules.area_control import REGION_CONFIG
                from models.enums import Region
                found = False
                for reg, cfg in REGION_CONFIG.items():
                    if reg.value == want_region and loc_id in cfg.get("locations", []):
                        found = True
                        break
                if not found:
                    continue

            # Neutral-only from top-level (not filter)
            if neutral_only and loc.controller not in (ControlState.NEUTRAL, ControlState.EMPTY):
                continue

            # Cannot convert own
            if loc.controller == player_cs:
                continue

            # Jin cannot convert capital
            player = state.get_player(player_id)
            if player and player.faction.value == "jin" and loc_id == "建康":
                continue

            valid.append(loc_id)

        return valid

    @staticmethod
    def _pick_target(state, player_id, resolver, valid, event_type, extra_info=None):
        """Helper: ask agent to select from valid targets."""
        if not valid or not resolver.select_target_callback:
            return None
        prompt = {"type": event_type, "options": valid}
        if extra_info:
            prompt.update(extra_info)
        return resolver.select_target_callback(player_id, prompt)


# ============================================================
# Status operators (prestige / contribution / order / culture)
# ============================================================

@register
class SpreadCultureOperator(EffectOperator):
    effect_type = EffectType.SPREAD_CULTURE

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.special_actions import SpreadCultureAction
        result = ResolveResult()
        if not resolver.action_system:
            return result

        culture = step.params.get("culture")
        if not culture:
            result.events.append({
                "type": "spread_culture_requested",
                "skipped": True, "reason": "no_culture_specified",
            })
            return result

        # 1. Hardcoded target_region in params
        if step.params.get("target_region"):
            action = SpreadCultureAction(
                player_id=player_id,
                culture_type=culture,
                target_region=step.params["target_region"],
            )
            r = resolver.action_system.execute(state, action)
            result.events.extend(r.events if r.success else [])
            if not r.success:
                if not r.success: result.errors.append(r.error or "action failed")
            return result

        # 2. Agent selects region
        valid_regions = self._get_valid_regions(state, player_id, culture)
        if valid_regions and resolver.select_target_callback:
            prompt = {
                "type": "spread_culture_requested",
                "options": valid_regions,
                "culture": culture,
            }
            chosen = resolver.select_target_callback(player_id, prompt)
            if chosen:
                action = SpreadCultureAction(
                    player_id=player_id,
                    culture_type=culture,
                    target_region=chosen,
                )
                r = resolver.action_system.execute(state, action)
                result.events.extend(r.events if r.success else [])
                if not r.success:
                    if not r.success: result.errors.append(r.error or "action failed")
            else:
                result.events.append({
                    "type": "spread_culture_requested",
                    "culture": culture, "skipped": True, "reason": "no_choice",
                })
        elif valid_regions:
            # No callback — just pick first valid region (deterministic fallback)
            action = SpreadCultureAction(
                player_id=player_id,
                culture_type=culture,
                target_region=valid_regions[0],
            )
            r = resolver.action_system.execute(state, action)
            result.events.extend(r.events if r.success else [])
            if not r.success:
                if not r.success: result.errors.append(r.error or "action failed")
        else:
            result.events.append({
                "type": "spread_culture_requested",
                "culture": culture, "skipped": True, "reason": "no_valid_regions",
            })

        return result

    @staticmethod
    def _get_valid_regions(state, player_id, culture) -> list[str]:
        """Enumerate regions where the player can spread this culture.

        Valid if: player controls at least one location in the region, OR
        region is adjacent to a region that already has this culture marker.
        """
        from rules.area_control import REGION_CONFIG
        from models.enums import CultureType

        friendly = state.get_friendly_locations(player_id)
        culture_ct = CultureType(culture) if culture else None

        # Regions that already have culture markers on map
        regions_with_culture = set()
        for loc_id, loc in state.locations.items():
            if loc.culture_marker and loc.culture_marker == culture_ct:
                for reg, cfg in REGION_CONFIG.items():
                    if loc_id in cfg.get("locations", []):
                        regions_with_culture.add(reg)

        valid = []
        for reg, cfg in REGION_CONFIG.items():
            reg_locs = cfg.get("locations", [])
            # Player controls at least one location in this region
            controls = any(loc in friendly for loc in reg_locs)
            # Adjacent to a region that has this culture
            adjacent = reg in regions_with_culture
            # Initial culture match
            initial_culture = cfg.get("initial_culture", "")
            has_initial = (initial_culture == culture)

            if controls or adjacent or has_initial:
                valid.append(reg.value)

        return valid


@register
class RaiseOrderOperator(EffectOperator):
    effect_type = EffectType.RAISE_ORDER

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.special_actions import RaiseOrderAction
        result = ResolveResult()
        if not resolver.action_system:
            return result
        action = RaiseOrderAction(player_id=player_id, amount=step.params.get("amount", 1))
        r = resolver.action_system.execute(state, action)
        result.events.extend(r.events if r.success else [])
        return result


@register
class LowerOrderOperator(EffectOperator):
    effect_type = EffectType.LOWER_ORDER

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        from engine.actions.special_actions import LowerOrderAction
        result = ResolveResult()
        if not resolver.action_system:
            return result
        p = step.params
        action = LowerOrderAction(
            player_id=player_id,
            target_player_id=p.get("target_player", player_id),
            amount=p.get("amount", 1),
        )
        r = resolver.action_system.execute(state, action)
        result.events.extend(r.events if r.success else [])
        return result


@register
class RaisePrestigeOperator(EffectOperator):
    effect_type = EffectType.RAISE_PRESTIGE

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 1)
        if player:
            player.prestige = min(10, player.prestige + amount)
            result.events.append({"type": "raise_prestige", "amount": amount})
            resolver._fire_trigger("on_gain_prestige", player_id,
                                   {"amount": amount})
        return result


@register
class LowerPrestigeOperator(EffectOperator):
    effect_type = EffectType.LOWER_PRESTIGE

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 1)
        if player:
            player.prestige = max(0, player.prestige - amount)
            result.events.append({"type": "lower_prestige", "amount": amount})
        return result


@register
class RaiseContributionOperator(EffectOperator):
    effect_type = EffectType.RAISE_CONTRIBUTION

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 1)
        if player:
            player.contribution = min(9, player.contribution + amount)
            result.events.append({"type": "raise_contribution", "amount": amount})
            resolver._fire_trigger("on_gain_contribution", player_id,
                                   {"amount": amount})
        return result


@register
class LowerContributionOperator(EffectOperator):
    effect_type = EffectType.LOWER_CONTRIBUTION

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        amount = step.params.get("amount", 1)
        if player:
            player.contribution = max(0, player.contribution - amount)
            result.events.append({"type": "lower_contribution", "amount": amount})
        return result


@register
class RaiseCultureLevelOperator(EffectOperator):
    effect_type = EffectType.RAISE_CULTURE_LEVEL

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        culture = step.params.get("culture")
        amount = step.params.get("amount", 1)
        if player and culture:
            from models.enums import CultureType
            ct = CultureType(culture)
            current = player.culture_contributions.get(ct, 0)
            player.culture_contributions[ct] = min(10, current + amount)
            result.events.append({"type": "raise_culture_level", "culture": culture, "amount": amount})
        return result


@register
class GetExpeditionOperator(EffectOperator):
    effect_type = EffectType.GET_EXPEDITION

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        if player:
            player.has_expedition_marker = True
            result.events.append({"type": "expedition_gained"})
        return result


# ============================================================
# Special operators
# ============================================================

@register
class AddRefugeeOperator(EffectOperator):
    effect_type = EffectType.ADD_REFUGEE

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        count = step.params.get("count", 1)
        # TODO: Phase 2a — implement refugee supply population logic
        result.events.append({"type": "add_refugee_requested", "count": count})
        return result


@register
class PlaceArmyOperator(EffectOperator):
    effect_type = EffectType.PLACE_ARMY

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        p = step.params
        loc_id = p.get("location")
        amount = p.get("amount", 1)
        if loc_id:
            loc = state.locations.get(loc_id)
            if loc:
                loc.army_count = loc.army_count + amount if hasattr(loc, 'army_count') else amount
                result.events.append({"type": "place_army", "location": loc_id, "amount": amount})
        return result


@register
class RemoveArmyOperator(EffectOperator):
    effect_type = EffectType.REMOVE_ARMY

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        p = step.params
        loc_id = p.get("location")
        amount = p.get("amount", 1)
        if loc_id:
            loc = state.locations.get(loc_id)
            if loc and hasattr(loc, 'army_count'):
                loc.army_count = max(0, loc.army_count - amount)
                result.events.append({"type": "remove_army", "location": loc_id, "amount": amount})
        return result


@register
class RemoveFromGameOperator(EffectOperator):
    effect_type = EffectType.REMOVE_FROM_GAME

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Remove the current card from the game (not just discard)
        result.events.append({"type": "remove_from_game"})
        return result


@register
class ChooseOperator(EffectOperator):
    effect_type = EffectType.CHOOSE

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Meta type — choice resolution happens at the block level (_resolve_block)
        # Individual choice options are executed as their own steps
        result.events.append({"type": "choose", "options": len(step.params.get("options", []))})
        return result


@register
class ConditionalOperator(EffectOperator):
    effect_type = EffectType.CONDITIONAL

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Meta type — conditional logic is handled by the condition check before
        # _execute_step is called. The sub-effect within is executed as a nested step.
        sub = step.params.get("sub_effect")
        if sub and isinstance(sub, dict):
            from .effect_ast import EffectStep as ES
            nested = ES(
                effect_type=sub.get("effect_type", ""),
                params=sub.get("params", {}),
                source_text=sub.get("source_text", ""),
            )
            inner = resolver._execute_step(nested, state, player_id, context)
            result.events.extend(inner.events)
            result.errors.extend(inner.errors)
        return result


@register
class NoopOperator(EffectOperator):
    effect_type = EffectType.NOOP

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        return ResolveResult()


@register
class RawOperator(EffectOperator):
    effect_type = EffectType.RAW

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        result.events.append({"type": "raw_effect", "text": step.source_text})
        return result
