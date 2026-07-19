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
        target = step.params.get("target", "main")  # "main" or "national"
        discarded = []
        for _ in range(count):
            if player and player.hand:
                discarded.append(player.hand.pop())
        if discarded:
            events = state.discard_cards(
                player_id, discarded, target=target, source="hand",
                reason="effect")
            result.events.extend(events)
            for _ in discarded:
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
class ReshuffleEmperorOperator(EffectOperator):
    """重洗君主牌堆：shuffle emperor deck and reset Sima prestige from new top card."""
    effect_type = EffectType.RESHUFFLE_EMPEROR

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        import random as _random
        result = ResolveResult()
        if not state.emperor or not state.emperor.emperor_deck:
            result.events.append({"type": "reshuffle_emperor",
                                  "skipped": True, "reason": "no_emperor_deck"})
            return result
        rng = _random.Random(state.seed)
        rng.shuffle(state.emperor.emperor_deck)
        new_emperor = state.emperor.emperor_deck[0]
        old_emperor_name = getattr(state.emperor.current_emperor, 'name', '?')
        state.emperor.current_emperor = new_emperor
        state.emperor.age = 1
        state.emperor.active_tasks = []
        if hasattr(new_emperor, 'initial_prestige'):
            state.sima.prestige = new_emperor.initial_prestige
        result.events.append({"type": "reshuffle_emperor",
                              "old_emperor": old_emperor_name,
                              "new_emperor": new_emperor.name,
                              "sima_prestige": state.sima.prestige})
        return result


@register
class ArchiveCardOperator(EffectOperator):
    effect_type = EffectType.ARCHIVE_CARD

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        count = step.params.get("count", 1)
        card_type_filter = step.params.get("card_type")  # "court", "friend", "any", or None
        source = step.params.get("from")  # "staff", "hand", or None

        for _ in range(count):
            card = None

            if card_type_filter == "court":
                # Archive from court cards — ask agent to choose
                court = state.get_court_cards(player_id)
                if not court:
                    continue
                # Exclude cards with cannot_be_archived restriction
                eligible = [c for c in court
                            if "cannot_be_archived" not in (
                                c.definition.parsed_effect.restrictions
                                if c.definition.parsed_effect else [])]
                if not eligible:
                    continue
                if resolver.select_target_callback:
                    prompt = {
                        "type": "archive_card",
                        "title": "选择1张朝堂牌存档",
                        "options": [
                            {"id": c.definition.card_id,
                             "label": f"{c.name} (费用{c.cost}, 史书{c.definition.history_vp}vp)"}
                            for c in eligible
                        ],
                    }
                    chosen_id = resolver.select_target_callback(player_id, prompt)
                    if chosen_id:
                        for i, c in enumerate(court):
                            if c.definition.card_id == chosen_id:
                                card = court.pop(i)
                                break
            elif source == "staff":
                # Archive from staff area
                if player and player.staff_area:
                    if resolver.select_target_callback:
                        prompt = {
                            "type": "archive_card",
                            "title": "选择1张幕僚存档",
                            "options": [
                                {"id": c.definition.card_id,
                                 "label": f"{c.name} (史书{c.definition.history_vp}vp)"}
                                for c in player.staff_area
                            ],
                        }
                        chosen_id = resolver.select_target_callback(player_id, prompt)
                        if chosen_id:
                            for i, c in enumerate(player.staff_area):
                                if c.definition.card_id == chosen_id:
                                    # Fire on_card_leave triggers BEFORE removing from staff
                                    resolver.fire_card_leave_triggers(
                                        c, player_id, state,
                                        context={"source": "archive_from_staff"})
                                    card = player.staff_area.pop(i)
                                    break
            else:
                # Default: archive from hand (last card)
                if player and player.hand:
                    card = player.hand.pop()

            if card:
                player.history_area.append(card)
                player.vp += card.definition.history_vp
                result.events.append({"type": "archive_card", "card": card.name})
                resolver._fire_trigger("on_archive", player_id,
                                       {"card": card})
                from models.enums import FactionType
                if player.faction == FactionType.JIN:
                    result.events.extend(state.add_contribution(player_id, 1))
        return result


@register
class ArchiveCourtOperator(EffectOperator):
    effect_type = EffectType.ARCHIVE_COURT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        # Remove cards from court to national discard (NOT main discard)
        court = state.get_court_cards(player_id)
        count = step.params.get("count", 1)
        abandoned = []
        for _ in range(count):
            if court:
                abandoned.append(court.pop())
        if abandoned:
            events = state.discard_cards(
                player_id, abandoned, target="national", source="court",
                reason="archive_court")
            result.events.extend(events)
        return result


@register
class PlayCardOperator(EffectOperator):
    effect_type = EffectType.PLAY_CARD

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        count = step.params.get("count", 1)
        may = step.params.get("may", False)
        free = step.params.get("free", False)
        card_type_filter = step.params.get("card_type")  # e.g. "friend" for 刘裕 active
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
                            # Handle free: temporarily grant military to cover cost
                            if free:
                                card_cost = played.definition.cost if played.definition else 0
                                if card_cost > 0 and player:
                                    player.military += card_cost
                            r = resolver.action_system.execute(state, action)
                            result.events.extend(r.events if r.success else [])
                            if not r.success:
                                if not r.success: result.errors.append(r.error or "action failed")
                        break
            elif may and player:
                # may=True without card_id: grant extra hand action so the player
                # can choose to play a card (or skip — logged at end of turn).
                player.extra_hand_actions += 1
                if card_type_filter:
                    player.extra_hand_action_filter = card_type_filter
                result.events.append({
                    "type": "extra_action_granted", "action_type": "hand_action",
                    "count": 1, "may": True, "free": free,
                    "card_type": card_type_filter, "filter": filter_spec,
                    "source": "play_card_effect",
                })
            else:
                result.events.append({
                    "type": "play_card_requested", "count": count,
                    "filter": filter_spec, "index": i, "free": free,
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
            from models.enums import CardType
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
                        result.errors.append(r.error or "action failed")
                elif resolver.select_target_callback:
                    # No card_id specified — ask agent to choose from court
                    court = state.get_court_cards(player_id)
                    if not court:
                        result.events.append({
                            "type": "draft_requested",
                            "count": count, "filter": filter_spec, "index": i,
                            "skipped": True, "reason": "empty_court",
                        })
                        continue

                    # Apply filter if specified
                    candidates = court
                    if filter_spec:
                        marker = filter_spec.get("marker")
                        if marker:
                            candidates = [c for c in court
                                         if c.definition.has_marker(marker)]
                        card_type_filter = filter_spec.get("card_type")
                        if card_type_filter:
                            ct = CardType(card_type_filter) if isinstance(card_type_filter, str) else card_type_filter
                            candidates = [c for c in candidates if c.card_type == ct]

                    # Exclude cards with cannot_be_drafted restriction
                    candidates = [c for c in candidates
                                  if "cannot_be_drafted" not in (
                                      c.definition.parsed_effect.restrictions
                                      if c.definition.parsed_effect else [])]

                    # Exclude cards whose play_condition is not met
                    candidates = [c for c in candidates
                                  if not (c.definition.parsed_effect
                                          and c.definition.parsed_effect.play_condition)
                                  or resolver.check_condition(
                                      c.definition.parsed_effect.play_condition,
                                      state, player_id)]

                    if not candidates:
                        result.events.append({
                            "type": "draft_requested",
                            "count": count, "filter": filter_spec, "index": i,
                            "skipped": True, "reason": "no_matching_cards",
                        })
                        continue

                    prompt = {
                        "type": "draft_card",
                        "title": f"选择1张候选策略牌征发 ({i+1}/{count})",
                        "options": [
                            {"id": c.definition.card_id,
                             "label": f"{c.name} (+{c.definition.resource_option_army}军/+{c.definition.resource_option_vp}vp)"}
                            for c in candidates
                        ],
                    }
                    chosen_id = resolver.select_target_callback(player_id, prompt)
                    if chosen_id:
                        action = LevyAction(player_id=player_id, card_id=chosen_id)
                        r = resolver.action_system.execute(state, action)
                        result.events.extend(r.events if r.success else [])
                        if not r.success:
                            result.errors.append(r.error or "action failed")
                    else:
                        result.events.append({
                            "type": "draft_requested",
                            "count": count, "filter": filter_spec, "index": i,
                            "skipped": True, "reason": "no_choice",
                        })
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
                "title": {"march_requested": "选择进军目标",
                         "occupy_requested": "选择占据目标",
                         "fortify_requested": "选择加固目标"}.get(self.event_type, "选择目标"),
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


# ============================================================
# Passive-effect operators (triggered via _check_triggers)
# ============================================================

@register
class MarchCostReductionOperator(EffectOperator):
    """Passive: reduce march cost by N.

    The cost reduction is applied PRE-PAYMENT by MarchAction._calculate_cost()
    via GameState.query_march_cost_reduction(). This operator fires after the
    march (via _check_triggers) and handles:
      - Per-turn limit tracking (increment counter)
      - Event emission for logging/display

    It does NOT refund military — that would double-count since the cost
    was already reduced before payment.
    """

    effect_type = "march_cost_reduction"

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        if not player:
            return result

        amount = step.params.get("amount", 0)
        per_turn_limit = step.params.get("per_turn_limit", 999)

        # Per-card per-turn tracking
        card_id = (context or {}).get("passive_card_id", "unknown")
        key = f"{card_id}:march_cost_reduction"
        used = player.passive_trigger_count.get(key, 0)

        if used >= per_turn_limit:
            return result

        # Cost reduction was already applied pre-payment in _calculate_cost().
        # Here we only update the per-turn counter and emit the event.
        # We do NOT refund military — that would double-count.
        player.passive_trigger_count[key] = used + 1
        result.events.append({
            "type": "march_cost_reduction",
            "amount": amount,
            "card_id": card_id,
            "remaining": per_turn_limit - (used + 1),
            "applied": "pre_cost",  # indicates reduction was in cost calc, not refund
        })

        return result


@register
class RegionRewardOverrideOperator(EffectOperator):
    """Passive: override region control VP rewards.

    Trigger: on_region_reward
    Params: partial (int), full (int) — VP for partial/full control
    """

    effect_type = "region_reward_override"

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        if not player:
            return result

        partial_vp = step.params.get("partial", 0)
        full_vp = step.params.get("full", 1)

        # Store override on the player for the region reward phase to read.
        player.region_reward_override = {
            "partial": partial_vp,
            "full": full_vp,
        }
        result.events.append({
            "type": "region_reward_override",
            "partial": partial_vp,
            "full": full_vp,
        })

        return result


@register
class MarchOperator(_TargetedMapOperator):
    effect_type = EffectType.MARCH
    event_type = "march_requested"
    context_key = "march_targets"

    def _get_valid_targets(self, state, player_id, step):
        """Enemy or neutral locations adjacent to own locations (not allies/Sima).

        Uses get_adjacency_source_locations() which implements:
          - Normal: own locations only
          - Expedition marker: all friendly locations
          - Fallback (0 own locations): Jin→all friendly, North→河北/幽燕/关外
        """
        sources = state.get_adjacency_source_locations(player_id)
        player_cs = state._player_control_state(player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            if loc.is_friendly_to(player_cs):
                continue
            neighbors = state.get_adjacent_locations(loc_id)
            if any(n in sources for n in neighbors):
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
                        # Pre-grant the reduction, then let action.execute() deduct
                        # the full cost. Net: player pays (cost - reduction).
                        # e.g. cost=3, reduction=2 → grant 2, deduct 3 → net -1 ✓
                        player.military += reduction
                        r = resolver.action_system.execute(state, action)
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
        """Empty/neutral locations adjacent to own locations (not allies/Sima).

        Uses get_adjacency_source_locations() which implements the fallback rule
        for players with 0 own locations (Jin→all friendly, North→河北/幽燕/关外).
        """
        sources = state.get_adjacency_source_locations(player_id)
        valid = []
        for loc_id, loc in state.locations.items():
            if loc.controller != ControlState.EMPTY:
                continue
            neighbors = state.get_adjacent_locations(loc_id)
            if any(n in sources for n in neighbors):
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

        # 0. Context-provided location (from targeted_effect location resolution)
        ctx_loc = (context or {}).get("target_location")
        if ctx_loc:
            action = ConvertAction(
                player_id=player_id,
                target_location=ctx_loc,
                neutral_only=neutral_only,
            )
            r = resolver.action_system.execute(state, action)
            result.events.extend(r.events if r.success else [])
            if not r.success:
                if not r.success: result.errors.append(r.error or "action failed")
            return result

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
                            from_filtered_choice=True,
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
        adjacency_sources = state.get_adjacency_source_locations(player_id)
        player_cs = state._player_control_state(player_id)

        for loc_id, loc in state.locations.items():
            # Adjacent filter — requires adjacency to own forces
            # (or all friendly forces if expedition marker is active)
            if filter_spec.get("adjacent"):
                neighbors = state.get_adjacent_locations(loc_id)
                if not any(n in adjacency_sources for n in neighbors):
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
        prompt = {
            "type": event_type,
            "title": {"convert_requested": "选择转化目标",
                     "march_requested": "选择进军目标",
                     "occupy_requested": "选择占据目标",
                     "fortify_requested": "选择加固目标"}.get(event_type, "选择目标"),
            "options": valid,
        }
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
            # No culture specified — let the agent choose which culture to spread
            # (e.g. 鸠摩罗什 active: "传播1次文化")
            if resolver.select_target_callback:
                prompt = {
                    "type": "spread_culture_requested",
                    "title": "选择要传播的文化类型",
                    "options": [
                        {"id": "confucianism", "label": "儒学"},
                        {"id": "taoism", "label": "玄学"},
                        {"id": "buddhism", "label": "佛学"},
                    ],
                }
                culture = resolver.select_target_callback(player_id, prompt)
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
            culture_label = {"confucianism": "儒学", "taoism": "玄学",
                           "buddhism": "佛学"}.get(culture, culture)
            prompt = {
                "type": "spread_culture_requested",
                "title": f"选择传播{culture_label}的目标区域",
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
                target_region=valid_regions[0]["id"],
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
    def _get_valid_regions(state, player_id, culture) -> list[dict]:
        """Enumerate regions where the player can spread this culture.

        Rulebook §5.1.6: valid if ANY of:
        - 己方控制该区域 (region has a friendly control marker —
          partial or full control per §"区域控制", not merely a
          single friendly location)
        - 该区域与该文化已存在的区域相邻 (adjacent to a region that
          already has this culture marker)
        - 初始文化 (region has this culture as its initial_culture)

        Returns list of dicts: {"id": region_value, "label": region_value, "reason": str}
        """
        from rules.area_control import REGION_CONFIG, get_adjacent_regions
        from models.enums import CultureType, ControlState

        culture_ct = CultureType(culture) if culture else None

        # Regions that already have culture markers of this type on the map
        regions_with_culture = set()
        for loc_id, loc in state.locations.items():
            if loc.culture_marker and loc.culture_marker == culture_ct:
                for reg, cfg in REGION_CONFIG.items():
                    if loc_id in cfg.get("locations", []):
                        regions_with_culture.add(reg)

        valid = []
        for reg, cfg in REGION_CONFIG.items():
            # Rulebook §"区域控制": region is controlled only if a
            # control marker is present (partial: > threshold; full: all).
            rs = state.regions.get(reg)
            if rs and rs.control_marker is not None:
                if player_id == "north":
                    controls = (rs.control_marker == ControlState.NORTH)
                else:
                    controls = (rs.control_marker != ControlState.NORTH)
            else:
                controls = False
            # Adjacent to a region that already has this culture marker on the map
            adjacent_regions = get_adjacent_regions(reg)
            adjacent = bool(adjacent_regions & regions_with_culture)
            # Initial culture match (for regions that natively have this culture)
            initial_culture = cfg.get("initial_culture", "")
            has_initial = (initial_culture == culture)

            if controls or adjacent or has_initial:
                reasons = []
                if controls:
                    reasons.append("已控制")
                if adjacent:
                    adj_names = ", ".join(r.value for r in (adjacent_regions & regions_with_culture))
                    reasons.append(f"与[{adj_names}]相邻")
                if has_initial:
                    reasons.append("初始文化")
                valid.append({
                    "id": reg.value,
                    "label": reg.value,
                    "reason": "、".join(reasons),
                })

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
            events = state.add_prestige(player_id, amount)
            result.events.extend(events)
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
            events = state.add_contribution(player_id, amount)
            result.events.extend(events)
            # on_gain_contribution trigger is now fired inside add_contribution()
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
        target = step.params.get("target", "")
        # TODO: Phase 2a — implement refugee supply population logic
        result.events.append({"type": "add_refugee_requested",
                              "count": count, "target": target})
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
        from .effect_ast import EffectStep as ES
        result = ResolveResult()
        # Retrieve options from params (placed there by _dict_to_step
        # when compiled JSON has choice_options at step level)
        options = step.params.get("choice_options") or step.params.get("options", [])

        # choice_index resolution:
        #  1. step.params.get("choice_index") — explicitly specified by caller
        #  2. context.get("_step_choice_index") — passed through from an outer choose
        #  3. resolver.make_choice_callback — ask the agent (used for 刘穆之, 桓石虔, etc.)
        #  NOTE: explicitly does NOT use context.get("choice_index") which is for
        #        block-level choice_options (set by ActivateEffectAction)
        choice_idx = step.params.get("choice_index")
        if choice_idx is None:
            choice_idx = (context or {}).get("_step_choice_index")
        if choice_idx is None and options and resolver.make_choice_callback:
            # Build prompt and ask agent to choose
            prompt = {
                "type": "choose_effect",
                "title": step.params.get("prompt_text", "选择一个选项"),
                "options": [],
            }
            for i, opt_steps in enumerate(options):
                # Summarize each option from its steps
                labels = []
                for s in opt_steps:
                    if isinstance(s, dict):
                        et = s.get("effect_type", "")
                        p = s.get("params", {})
                        cnt = p.get("count", p.get("amount", 1))
                        try:
                            cnt = int(cnt)
                        except (ValueError, TypeError):
                            cnt = 1
                        # Include culture type in label for culture-related effects
                        culture = p.get("culture", "")
                        culture_label = ""
                        if culture:
                            culture_map = {
                                "confucianism": "儒学", "taoism": "玄学",
                                "buddhism": "佛学",
                            }
                            culture_label = f"[{culture_map.get(culture, culture)}]"
                        label_map = {
                            "draw_cards": f"摸{cnt}张牌",
                            "draft": f"征发{cnt}张候选策略牌" if cnt > 1 else "征发1张候选策略牌",
                            "play_card": f"打出{cnt}张牌" if cnt > 1 else "打出1张牌",
                            "gain_military": f"+{cnt}军力",
                            "gain_vp": f"+{cnt}VP",
                            "spread_culture": f"传播{culture_label}文化" if culture_label else "传播文化",
                            "raise_culture_contribution": f"提高{culture_label}贡献度" if culture_label else f"提高文化贡献度",
                            "raise_culture_level": f"提高{culture_label}等级" if culture_label else "提高文化等级",
                            "remove_culture_marker": f"移除{culture_label}标记" if culture_label else "移除文化标记",
                            "archive_card": "存档",
                            "search": "检索",
                        }
                        labels.append(label_map.get(et, et))
                prompt["options"].append({
                    "id": str(i),
                    "label": f"选项{i+1}: {'，'.join(labels)}" if labels else f"选项{i+1}",
                })
            choice_idx = resolver.make_choice_callback(player_id, prompt)

        if choice_idx is None:
            choice_idx = 0

        chosen_label = f"option_{choice_idx + 1}" if options else "none"
        result.events.append({"type": "choose",
                              "options": len(options),
                              "chosen": choice_idx,
                              "chosen_label": chosen_label})

        # Execute the chosen option's sub-steps
        if options and 0 <= choice_idx < len(options):
            chosen_option = options[choice_idx]
            for sub_step_dict in chosen_option:
                if isinstance(sub_step_dict, dict):
                    # Build params from the dict, moving step-level keys into params
                    # (mirrors _dict_to_step logic for filter/target/choice_options)
                    sub_params = dict(sub_step_dict.get("params", {}))
                    for key in ("filter", "choice_options", "target"):
                        if key in sub_step_dict and sub_step_dict[key] is not None:
                            sub_params[key] = sub_step_dict[key]
                    nested = ES(
                        effect_type=sub_step_dict.get("effect_type", ""),
                        params=sub_params,
                        source_text=sub_step_dict.get("source_text", ""),
                        condition=sub_step_dict.get("condition"),
                    )
                    inner = resolver._execute_step(nested, state, player_id, context)
                    result.events.extend(inner.events)
                    result.errors.extend(inner.errors)
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


@register
class StealRandomCardOperator(EffectOperator):
    """Randomly steal card(s) from target player's hand.

    Used by 轻骑兵 and other cards via targeted_effect:
    target a player, then steal_random_card from them.
    The source_player (who activated the card) is read from context.
    """
    effect_type = "steal_random_card"

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        import random
        result = ResolveResult()
        count = step.params.get("count", 1)
        target = state.get_player(player_id)
        if not target or not target.hand:
            result.events.append({"type": "steal_random_card",
                                  "skipped": True, "reason": "no_cards_in_hand",
                                  "from_player": player_id})
            return result

        # Steal random cards from target's hand
        # player_id = victim (target of steal)
        # context.source_player = original card activator (who receives stolen cards)
        source_player_id = (context or {}).get("source_player", player_id)
        source_player = state.get_player(source_player_id)
        rng = random.Random(state.seed + state.round + hash(player_id) % 10000)
        stolen = []
        for _ in range(min(count, len(target.hand))):
            idx = rng.randint(0, len(target.hand) - 1)
            card = target.hand.pop(idx)
            if source_player and source_player_id != player_id:
                source_player.hand.append(card)
                stolen.append({"card": card.name, "from": player_id, "to": source_player_id})
            else:
                state.main_discard.append(card)
                stolen.append({"card": card.name, "from": player_id, "to": "discard"})

        for s in stolen:
            result.events.append({"type": "steal_random_card",
                                  "card": s["card"], "from_player": s["from"],
                                  "to_player": s["to"]})
        return result


@register
class ExtraActionOperator(EffectOperator):
    """Grant an extra action (court_action or hand_action) this turn.

    Used by cards like 慕容儁 (extra court action) and 苻坚 (extra hand action).
    The operator increments the player's extra action counter; the action system
    reads this counter to determine availability.
    """
    effect_type = EffectType.EXTRA_ACTION

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()
        player = state.get_player(player_id)
        if not player:
            return ResolveResult(success=False, errors=["Player not found"])

        action_type = step.params.get("action_type", "court_action")
        may = step.params.get("may", False)
        count = step.params.get("count", 1)

        if action_type == "court_action":
            player.extra_court_actions += count
        elif action_type == "hand_action":
            player.extra_hand_actions += count

        result.events.append({
            "type": "extra_action_granted",
            "action_type": action_type,
            "count": count,
            "may": may,
        })
        return result


@register
class TargetedEffectOperator(EffectOperator):
    """Meta-effect: resolve sub_effects against a different target.

    Used by 21+ cards (功高不赏, 衣冠南渡, 鸩酒, etc.) to apply effects
    to players/cards/locations other than the card activator.

    Target spec structure:
      {
        "type": "player" | "jin_player" | "north_player" | "other_jin_player" | ...,
        "selection": "choose" | "each" | "random" | "all",
        "count": 1,
        "filters": [{"type": "highest_contribution"}, ...]
      }
    """
    effect_type = EffectType.TARGETED_EFFECT

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()

        target_spec = step.params.get("target", {})
        if not target_spec:
            return ResolveResult(success=False, errors=["targeted_effect: no target spec"])

        # Normalise sub_effect/sub_effects to a list
        sub_effects = step.params.get("sub_effects", [])
        if not sub_effects:
            sub = step.params.get("sub_effect")
            if sub:
                sub_effects = [sub]

        if not sub_effects:
            return ResolveResult(success=False, errors=["targeted_effect: no sub_effects"])

        # Enrich context with source player (original card activator)
        enriched_ctx = dict(context or {})
        enriched_ctx["source_player"] = player_id

        t = target_spec.get("type", "player")

        # ── Location targets ──────────────────────────────────
        if t in ("location", "sima"):
            location_ids = self._resolve_location_targets(
                target_spec, state, player_id, resolver)
            if not location_ids:
                result.events.append({
                    "type": "targeted_effect",
                    "target_type": t,
                    "targets_found": 0,
                    "skipped": True,
                    "reason": "no_matching_locations",
                })
                return result

            for loc_id in location_ids:
                # Pass location_id through context for sub-effects
                loc_ctx = dict(enriched_ctx)
                loc_ctx["target_location"] = loc_id
                for sub_dict in sub_effects:
                    sub_step = self._dict_to_effect_step(sub_dict)
                    sub_result = resolver._execute_step(
                        sub_step, state, player_id, loc_ctx)
                    result.events.extend(sub_result.events)
                    result.errors.extend(sub_result.errors)

            result.events.insert(0, {
                "type": "targeted_effect",
                "target_type": t,
                "targets_found": len(location_ids),
                "targets": location_ids,
            })
            return result

        # ── Player targets ────────────────────────────────────
        target_pids = self._resolve_target_players(
            target_spec, state, player_id, resolver)

        if not target_pids:
            result.events.append({
                "type": "targeted_effect",
                "target_type": t,
                "targets_found": 0,
                "skipped": True,
                "reason": "no_matching_targets",
            })
            return result

        # Apply sub-effects to each target player
        for target_pid in target_pids:
            for sub_dict in sub_effects:
                sub_step = self._dict_to_effect_step(sub_dict)
                sub_result = resolver._execute_step(
                    sub_step, state, target_pid, enriched_ctx)
                result.events.extend(sub_result.events)
                result.errors.extend(sub_result.errors)

        result.events.insert(0, {
            "type": "targeted_effect",
            "target_type": t,
            "targets_found": len(target_pids),
            "targets": target_pids,
        })
        return result

    # ---- target resolution ------------------------------------------------

    def _resolve_target_players(self, spec, state, source_pid, resolver):
        """Return list of player IDs matching the target spec."""
        t = spec.get("type", "player")
        selection = spec.get("selection", "choose")
        count = spec.get("count", 1)
        filters = spec.get("filters", [])

        candidates = self._collect_candidates(t, state, source_pid)
        candidates = self._apply_filters(candidates, filters, state)

        if selection == "each" or selection == "all":
            return candidates

        # "random": pick randomly
        if selection == "random":
            import random
            rng = random.Random(state.seed + state.round)
            return rng.sample(candidates, min(count, len(candidates))) if candidates else []

        # "choose": ask agent via callback
        if selection == "choose" and len(candidates) > 1:
            if resolver and resolver.select_target_callback:
                prompt = {
                    "type": "player",
                    "options": candidates,
                    "message": f"Choose target for effect (type={t})",
                }
                chosen = resolver.select_target_callback(source_pid, prompt)
                if chosen and chosen in candidates:
                    return [chosen]

        # Default: first N candidates
        return candidates[:count]

    @staticmethod
    def _collect_candidates(target_type, state, source_pid):
        """Collect candidate player IDs based on target type."""
        all_players = state.get_all_players()
        from models.enums import FactionType

        if target_type == "player":
            return [p.player_id for p in all_players]

        if target_type == "jin_player":
            return [p.player_id for p in all_players
                    if p.faction == FactionType.JIN]

        if target_type == "north_player":
            return [p.player_id for p in all_players
                    if p.faction == FactionType.NORTH]

        if target_type == "other_jin_player":
            return [p.player_id for p in all_players
                    if p.player_id != source_pid
                    and p.faction == FactionType.JIN]

        if target_type == "other_player":
            return [p.player_id for p in all_players
                    if p.player_id != source_pid]

        if target_type == "friendly_player":
            source = state.get_player(source_pid)
            if source:
                return [p.player_id for p in all_players
                        if p.faction == source.faction]

        # card / friend_card / location types — return source for now
        return [source_pid]

    # ---- location target resolution -----------------------------------------

    def _resolve_location_targets(self, spec, state, source_pid, resolver):
        """Return list of location IDs matching the target spec."""
        from models.enums import ControlState

        selection = spec.get("selection", "choose")
        count = spec.get("count", 1)
        filters = spec.get("filters", [])

        # Collect candidates from all locations
        candidates = list(state.locations.keys())
        candidates = self._apply_location_filters(candidates, filters, state, source_pid)

        if selection == "each" or selection == "all":
            return candidates[:count] if count else candidates

        if selection == "random":
            import random
            rng = random.Random(state.seed + state.round)
            return rng.sample(candidates, min(count, len(candidates))) if candidates else []

        if selection == "choose" and len(candidates) > 1:
            if resolver and resolver.select_target_callback:
                prompt = {
                    "type": "location",
                    "options": candidates,
                    "message": f"Choose location for effect (type={spec.get('type', '?')})",
                }
                chosen = resolver.select_target_callback(source_pid, prompt)
                if chosen and chosen in candidates:
                    return [chosen]

        return candidates[:count]

    @staticmethod
    def _apply_location_filters(candidates, filters, state, source_pid):
        """Filter location candidates by filter specs."""
        if not filters:
            return candidates

        from models.enums import ControlState
        player_cs = state._player_control_state(source_pid)

        for f in filters:
            ft = f.get("type", "")
            controller = f.get("controller")
            if controller:
                if controller == "sima":
                    candidates = [lid for lid in candidates
                                  if state.locations.get(lid) and
                                  state.locations[lid].controller == ControlState.SIMA]
                elif controller == "jin":
                    jin_states = {ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3}
                    candidates = [lid for lid in candidates
                                  if state.locations.get(lid) and
                                  state.locations[lid].controller in jin_states]
                elif controller == "neutral":
                    candidates = [lid for lid in candidates
                                  if state.locations.get(lid) and
                                  state.locations[lid].controller in (ControlState.NEUTRAL, ControlState.EMPTY)]
                elif controller == "north":
                    candidates = [lid for lid in candidates
                                  if state.locations.get(lid) and
                                  state.locations[lid].controller == ControlState.NORTH]
                elif controller == "not_jin_controlled":
                    jin_states = {ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3}
                    candidates = [lid for lid in candidates
                                  if state.locations.get(lid) and
                                  state.locations[lid].controller not in jin_states]
                continue

            if ft == "not_jin_controlled":
                jin_states = {ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3}
                candidates = [lid for lid in candidates
                              if state.locations.get(lid) and
                              state.locations[lid].controller not in jin_states]
            elif ft == "not_fortified":
                candidates = [lid for lid in candidates
                              if state.locations.get(lid) and
                              not state.locations[lid].is_fortified]
            elif controller is None and "culture_region" in f:
                culture_type = f.get("culture_region", "")
                from rules.area_control import REGION_CONFIG
                from models.enums import Region
                locs_in_culture_region = set()
                for reg, cfg in REGION_CONFIG.items():
                    if cfg.get("initial_culture") == culture_type:
                        locs_in_culture_region.update(cfg.get("locations", []))
                    # Also match regions that have this culture placed
                    for loc_id in cfg.get("locations", []):
                        loc = state.locations.get(loc_id)
                        if loc and loc.culture_marker and loc.culture_marker.value == culture_type:
                            locs_in_culture_region.update(cfg.get("locations", []))
                candidates = [lid for lid in candidates if lid in locs_in_culture_region]

        return candidates

    @staticmethod
    def _apply_filters(candidates, filters, state):
        """Filter/sort candidates by filter specs."""
        if not filters:
            return candidates

        for f in filters:
            ft = f.get("type", "")
            if ft == "highest_contribution":
                candidates = TargetedEffectOperator._filter_highest(
                    candidates, state, "contribution")
            elif ft == "lowest_contribution":
                candidates = TargetedEffectOperator._filter_highest(
                    candidates, state, "contribution", reverse=True)
            elif ft == "highest_prestige":
                candidates = TargetedEffectOperator._filter_highest(
                    candidates, state, "prestige")
            elif ft in ("fewest_staff_slots", "fewest_empty_staff_slots"):
                candidates = TargetedEffectOperator._filter_highest(
                    candidates, state, "staff_free_slots", reverse=True)
            elif ft == "highest_military":
                candidates = TargetedEffectOperator._filter_highest(
                    candidates, state, "military")

        return candidates

    @staticmethod
    def _filter_highest(candidates, state, attr, reverse=False):
        """Keep only candidates with the highest (or lowest) value of attr."""
        if not candidates:
            return []
        scored = []
        for pid in candidates:
            p = state.get_player(pid)
            if p:
                val = getattr(p, attr, 0)
                if callable(val):
                    val = val()
                scored.append((pid, val))
        if not scored:
            return []
        scored.sort(key=lambda x: x[1], reverse=not reverse)
        best_val = scored[0][1]
        return [pid for pid, val in scored if val == best_val]

    # ---- sub-effect deserialisation ---------------------------------------

    @staticmethod
    def _dict_to_effect_step(d):
        """Convert a sub_effect dict from compiled JSON back into an EffectStep."""
        from .effect_ast import EffectStep
        return EffectStep(
            effect_type=d.get("effect_type", ""),
            params=d.get("params", {}),
            condition=None,  # Conditions on sub-effects deferred
            source_text=d.get("source_text", ""),
        )


# ============================================================
# Aliases — register same operator under alternate names
# used in cards_compiled.json that don't match EffectType constants
# ============================================================

# choice (JSON) → choose (code)
OPERATOR_REGISTRY["choice"] = OPERATOR_REGISTRY["choose"]

# gain_prestige (JSON) → raise_prestige (code)
OPERATOR_REGISTRY["gain_prestige"] = OPERATOR_REGISTRY["raise_prestige"]

# lose_contribution (JSON) → lower_contribution (code)
OPERATOR_REGISTRY["lose_contribution"] = OPERATOR_REGISTRY["lower_contribution"]

# place_refugee (JSON) → add_refugee (code)
OPERATOR_REGISTRY["place_refugee"] = OPERATOR_REGISTRY["add_refugee"]

# raise_culture_contribution (JSON) → raise_culture_level (code)
OPERATOR_REGISTRY["raise_culture_contribution"] = OPERATOR_REGISTRY["raise_culture_level"]


# ============================================================
# Map-action variants with distinct semantics
# ============================================================

@register
class ConvertOwnToNeutralOperator(EffectOperator):
    """Convert friendly (own-controlled) locations to neutral.

    Used by 姚苌 passive: on leaving play, convert 2 own locations to neutral.
    """
    effect_type = EffectType.CONVERT_OWN_TO_NEUTRAL

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()

        # 0. Context-provided location (from targeted_effect location resolution)
        ctx_loc = (context or {}).get("target_location")
        if ctx_loc:
            loc = state.locations.get(ctx_loc)
            if loc:
                from models.enums import ControlState
                loc.controller = ControlState.NEUTRAL
                result.events.append({"type": "convert_own_to_neutral",
                                     "location": ctx_loc})
            return result

        count = step.params.get("count", 1)

        # Find player's own locations (not allies like Sima for Jin)
        own = state.get_own_locations(player_id)
        neutral_candidates = [lid for lid in own
                             if state.locations.get(lid)]

        if not neutral_candidates:
            result.events.append({"type": "convert_own_to_neutral",
                                  "skipped": True, "reason": "no_own_locations"})
            return result

        # Ask agent to choose
        chosen = []
        if resolver and resolver.select_target_callback:
            for _ in range(min(count, len(neutral_candidates))):
                prompt = {
                    "type": "location",
                    "options": [c for c in neutral_candidates if c not in chosen],
                    "message": f"Choose location to convert to neutral",
                }
                pick = resolver.select_target_callback(player_id, prompt)
                if pick and pick in neutral_candidates and pick not in chosen:
                    chosen.append(pick)

        if not chosen and neutral_candidates:
            chosen = neutral_candidates[:min(count, len(neutral_candidates))]

        for loc_id in chosen:
            loc = state.locations.get(loc_id)
            if loc:
                from models.enums import ControlState
                loc.controller = ControlState.NEUTRAL
                result.events.append({"type": "convert_own_to_neutral",
                                     "location": loc_id})

        return result


@register
class ConvertToNeutralOperator(EffectOperator):
    """Convert target locations to neutral (used in targeted_effect sub-effects).

    Used by 功高不赏 variant effects: convert locations to neutral.
    """
    effect_type = EffectType.CONVERT_TO_NEUTRAL

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()

        # 0. Context-provided location (from targeted_effect location resolution)
        ctx_loc = (context or {}).get("target_location")
        if ctx_loc:
            loc = state.locations.get(ctx_loc)
            if loc:
                from models.enums import ControlState
                loc.controller = ControlState.NEUTRAL
                result.events.append({"type": "convert_to_neutral",
                                     "location": ctx_loc})
            return result

        count = step.params.get("count", 1)

        # Find all non-neutral locations
        from models.enums import ControlState
        candidates = [lid for lid, loc in state.locations.items()
                     if loc.controller not in (ControlState.NEUTRAL, ControlState.EMPTY)]

        chosen = []
        if resolver and resolver.select_target_callback and candidates:
            for _ in range(min(count, len(candidates))):
                prompt = {
                    "type": "location",
                    "options": [c for c in candidates if c not in chosen],
                    "message": "Choose location to convert to neutral",
                }
                pick = resolver.select_target_callback(player_id, prompt)
                if pick and pick in candidates and pick not in chosen:
                    chosen.append(pick)

        if not chosen and candidates:
            chosen = candidates[:min(count, len(candidates))]

        for loc_id in chosen:
            loc = state.locations.get(loc_id)
            if loc:
                loc.controller = ControlState.NEUTRAL
                result.events.append({"type": "convert_to_neutral",
                                     "location": loc_id})

        return result


@register
class ConvertToSimaOperator(EffectOperator):
    """Convert target locations to Sima control.

    Used by 遣使请降: convert locations to Sima faction.
    """
    effect_type = EffectType.CONVERT_TO_SIMA

    def execute(self, step, state, player_id, context, resolver):
        from .effect_resolver import ResolveResult
        result = ResolveResult()

        # 0. Context-provided location (from targeted_effect location resolution)
        ctx_loc = (context or {}).get("target_location")
        if ctx_loc:
            loc = state.locations.get(ctx_loc)
            if loc:
                from models.enums import ControlState
                loc.controller = ControlState.SIMA
                result.events.append({"type": "convert_to_sima",
                                     "location": ctx_loc})
            return result

        count = step.params.get("count", 1)

        from models.enums import ControlState
        candidates = [lid for lid, loc in state.locations.items()
                     if loc.controller not in (ControlState.SIMA,)]

        chosen = []
        if resolver and resolver.select_target_callback and candidates:
            for _ in range(min(count, len(candidates))):
                prompt = {
                    "type": "location",
                    "options": [c for c in candidates if c not in chosen],
                    "message": "Choose location to convert to Sima",
                }
                pick = resolver.select_target_callback(player_id, prompt)
                if pick and pick in candidates and pick not in chosen:
                    chosen.append(pick)

        if not chosen and candidates:
            chosen = candidates[:min(count, len(candidates))]

        for loc_id in chosen:
            loc = state.locations.get(loc_id)
            if loc:
                loc.controller = ControlState.SIMA
                result.events.append({"type": "convert_to_sima",
                                     "location": loc_id})

        return result
        return result
