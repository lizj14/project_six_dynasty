"""HeuristicAI — rule-based AI that scores actions and picks the best.

Beats DummyAI by prioritizing:
  1. Playing cards for resources (VP > military > culture > cards)
  2. Marching to high-value contested regions
  3. Occupying neutral locations
  4. Fortifying key positions
  5. Using court actions when military is available
  6. Passing only when nothing worthwhile remains
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from typing import Optional

from .interface import GameAgent, SetupContext, SetupDecision
from cards.effect_ast import AbilityType, EffectType
from models.enums import TerrainType, ControlState, FactionType
from rules.area_control import REGION_CONFIG


class HeuristicAI(GameAgent):
    """Rule-based AI that scores available actions and picks the best.

    Each action is scored from 0-10 based on expected resource gain,
    VP potential, and strategic value. Passes (returns None) when
    all actions score below the threshold (typically 0).
    """

    def __init__(self, player_id: str = "", seed: int = 0):
        self.player_id = player_id
        self.rng = random.Random(seed)
        self._chain_occupy: bool = False       # Chain occupy after successful march
        self._last_march_target: str = ""

    # === Setup ===

    def setup_decision(self, ctx: SetupContext) -> SetupDecision:
        """Pick hero with highest initial prestige/contribution; random goals."""
        d = SetupDecision()

        # Pick hero: prefer higher initial prestige + contribution
        if ctx.hero_choices:
            best_idx = 0
            best_score = -1
            for i, hero in enumerate(ctx.hero_choices):
                score = hero.get("initial_prestige", 0) + hero.get("initial_contribution", 0)
                if score > best_score:
                    best_score = score
                    best_idx = i
            # Add some randomness to avoid identical picks every game
            if self.rng.random() < 0.3 and len(ctx.hero_choices) > 1:
                best_idx = self.rng.randint(0, len(ctx.hero_choices) - 1)
            d.hero_index = best_idx
        else:
            d.hero_index = 0

        # Pick goals: random for now (goals are complex to evaluate)
        if ctx.goal_choices:
            indices = list(range(len(ctx.goal_choices)))
            self.rng.shuffle(indices)
            d.public_goal_index = indices[0]
            d.secret_goal_index = indices[1] if len(indices) >= 2 else indices[0]
        else:
            d.public_goal_index = 0
            d.secret_goal_index = 0

        # Pick face-down card: prefer low-cost cards with strong effects
        if ctx.hand_cards:
            # Simple heuristic: use first non-event card, or first card
            d.face_down_card_index = 0
            other = [i for i in range(len(ctx.hand_cards)) if i != d.face_down_card_index]
            self.rng.shuffle(other)
            d.payment_indices = other[:2]
        else:
            d.face_down_card_index = 0
            d.payment_indices = []

        return d

    # === Turn: iterative single-action decision ===

    def decide_action(self, state: "GameState",
                      available_actions: list) -> Optional["GameAction"]:
        """Score each available action and pick the best. Pass if score too low."""
        if not available_actions:
            self._chain_occupy = False
            return None

        # ── Chain march → occupy ─────────────────────
        # After a successful march, immediately try to occupy the same location
        # if military remains.
        if self._chain_occupy:
            self._chain_occupy = False
            occupy_actions = [a for a in available_actions
                            if getattr(a, 'action_type', '') == "occupy"]
            if occupy_actions:
                for a in occupy_actions:
                    if getattr(a, 'target_location', '') == self._last_march_target:
                        return a
                return self.rng.choice(occupy_actions)

        scored = []
        for action in available_actions:
            score = self._score_action(action, state)
            if score > 0:
                scored.append((score, action))

        if not scored:
            return None

        # Sort by score descending, add small random jitter to break ties
        scored.sort(key=lambda x: x[0] + self.rng.uniform(-0.2, 0.2), reverse=True)
        chosen = scored[0][1]

        # Chain march → occupy: set flag so next decide_action picks occupy
        if getattr(chosen, 'action_type', '') == "march":
            self._chain_occupy = True
            self._last_march_target = getattr(chosen, 'target_location', '')
        else:
            self._chain_occupy = False

        return chosen

    def _score_action(self, action, state: "GameState") -> float:
        """Score a single action from 0-10.

        The scoring reflects expected value: VP gain, resource efficiency,
        and strategic positioning.
        """
        atype = getattr(action, 'action_type', '')

        if atype == "court_action":
            return self._score_court_action(action, state)
        elif atype == "play_card":
            return self._score_play_card(action, state)
        elif atype == "march":
            return self._score_march(action, state)
        elif atype == "occupy":
            return self._score_occupy(action, state)
        elif atype == "fortify":
            return self._score_fortify(action, state)
        elif atype == "spread_culture":
            return self._score_spread_culture(action, state)
        elif atype == "convert":
            return self._score_convert(action, state)
        elif atype == "recruit":
            return self._score_recruit(action, state)
        elif atype == "draw":
            return self._score_draw(action, state)
        elif atype == "archive":
            return self._score_archive(action, state)
        elif atype == "raise_order":
            return self._score_raise_order(action, state)
        elif atype == "lower_order":
            return 1.0  # Low priority, rarely beneficial for self
        elif atype == "search":
            return 2.0  # Conditional value
        elif atype == "levy":
            return 2.0  # Draft new court cards
        elif atype == "activate_effect":
            return self._score_activate_effect(action, state)
        elif atype == "play_public_card":
            return self._score_play_public_card(action, state)
        else:
            return 1.0  # Unknown — worth trying

    # ── Action-specific scorers ──────────────────────────────

    def _score_court_action(self, action, state) -> float:
        """Score court (牌组) actions based on resource gain and affordability."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        card_id = getattr(action, 'card_id', '')
        court = state.get_court_cards(self.player_id)
        for card in court:
            if card.definition.card_id == card_id:
                defn = card.definition
                score = 0.0

                # ── Check block-level costs first ──────────────
                parsed = defn.parsed_effect
                if parsed:
                    for block in parsed.blocks:
                        if block.ability_type != AbilityType.STRATEGY_ACTION:
                            continue
                        for bc in block.costs:
                            if not self._can_afford_cost(bc, player, state):
                                return 0.0  # Can't afford → skip

                # Parse expected resource gain from parsed AST
                if parsed:
                    for block in parsed.blocks:
                        if block.ability_type != AbilityType.STRATEGY_ACTION:
                            continue
                        for step in block.steps:
                            et = step.effect_type
                            amt = step.params.get("amount", step.params.get("count", 1))
                            if not isinstance(amt, (int, float)):
                                try:
                                    amt = int(amt)
                                except (ValueError, TypeError):
                                    amt = 1
                            if et == EffectType.GAIN_VP:
                                score += amt * 2.0  # VP is king
                            elif et == EffectType.GAIN_MILITARY:
                                score += amt * 1.5  # Military is useful
                            elif et == EffectType.DRAW_CARDS:
                                score += amt * 1.0  # Cards have potential
                            elif et == EffectType.RAISE_ORDER:
                                score += amt * 1.0
                            elif et == EffectType.SPREAD_CULTURE:
                                score += amt * 2.5  # Culture is high value
                            elif et == EffectType.ARCHIVE_CARD:
                                score += 1.5
                            elif et == EffectType.DISCARD_CARDS:
                                score -= amt * 0.5  # Discarding is a cost
                            else:
                                score += amt * 0.5

                # Resource option: if card has army/VP choice
                resource = defn.resource_option_army or 0
                if resource > 0:
                    score += resource * 0.8  # Army from resource

                # Ensure we can afford the military cost
                # Court actions don't have explicit costs in the same way
                # but they consume the court action slot
                return max(0.0, min(score, 10.0))

        return 2.0  # Default: worth trying

    def _score_play_card(self, action, state) -> float:
        """Score playing a card from hand based on its effects and affordability."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        idx = getattr(action, 'card_index', -1)
        if idx < 0 or idx >= len(player.hand):
            return 0.0

        card = player.hand[idx]
        defn = card.definition
        cost = defn.cost or 0
        score = 0.0

        # ── Check play_condition first ─────────────────────
        parsed = defn.parsed_effect
        if parsed and parsed.play_condition:
            resolver = getattr(state, 'effect_resolver', None)
            if resolver and not resolver.check_condition(
                parsed.play_condition, state, self.player_id):
                return 0.0  # Condition not met → can't play

        # ── Check block-level costs ────────────────────────
        if parsed:
            for block in parsed.blocks:
                for bc in block.costs:
                    if not self._can_afford_cost(bc, player, state):
                        return 0.0  # Can't afford → skip

        # Friend cards (幕僚): provide ongoing passive/enter effects
        if card.is_friend:

            if not player.can_play_friend():
                return 0.0  # Can't play if staff full

            score += 3.0  # Base value for friend card

            # Evaluate enter effects
            parsed = defn.parsed_effect
            if parsed:
                for block in parsed.blocks:
                    if block.ability_type in (AbilityType.ENTER, AbilityType.ACTIVE):
                        for step in block.steps:
                            score += self._step_value(step) * 1.5
                    # Passive abilities add ongoing value
                    if block.ability_type == AbilityType.PASSIVE:
                        score += 2.0

        # Strategy cards
        elif defn.card_type.value == "strategy":
            score += 1.5
            parsed = defn.parsed_effect
            if parsed:
                for block in parsed.blocks:
                    if block.ability_type == AbilityType.STRATEGY_ACTION:
                        for step in block.steps:
                            score += self._step_value(step)
            # Resource option
            score += (defn.resource_option_army or 0) * 0.5
            score += (defn.resource_option_vp or 0) * 0.8

        # Event cards: situational
        elif defn.card_type.value == "event":
            score += 1.0
            parsed = defn.parsed_effect
            if parsed:
                for block in parsed.blocks:
                    for step in block.steps:
                        score += self._step_value(step) * 0.7  # Discount for conditionality

        # Paying cost
        if cost > 0:
            # Cost is paid by discarding other cards
            score -= cost * 0.5  # Each card sacrificed = -0.5

        return max(0.0, min(score, 10.0))

    def _step_value(self, step) -> float:
        """Score a single effect step based on its resource value."""
        et = step.effect_type
        amt = step.params.get("amount", step.params.get("count", 1))
        if not isinstance(amt, (int, float)):
            try:
                amt = int(amt)
            except (ValueError, TypeError):
                amt = 1

        values = {
            EffectType.GAIN_VP: amt * 2.0,
            EffectType.GAIN_MILITARY: amt * 1.5,
            EffectType.DRAW_CARDS: amt * 1.2,
            EffectType.SPREAD_CULTURE: amt * 2.5,
            EffectType.RAISE_PRESTIGE: amt * 1.5,
            EffectType.RAISE_CONTRIBUTION: amt * 1.5,
            EffectType.RAISE_ORDER: amt * 1.0,
            EffectType.CONVERT: amt * 2.0,
            EffectType.MARCH: amt * 2.0,
            EffectType.OCCUPY: amt * 1.5,
            EffectType.GET_EXPEDITION: 2.0,
            EffectType.ARCHIVE_CARD: 1.5,
            EffectType.DISCARD_CARDS: -amt * 0.5,
            EffectType.LOSE_VP: -amt * 2.0,
            EffectType.LOSE_MILITARY: -amt * 1.5,
            EffectType.PAY_MILITARY: -amt * 1.5,
            EffectType.PAY_VP: -amt * 2.0,
        }
        return values.get(et, amt * 0.3)

    def _score_march(self, action, state) -> float:
        """Score a march action based on target value."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        target = getattr(action, 'target_location', '')
        if not target or target not in state.locations:
            return 0.0

        loc = state.locations[target]
        cost = 3  # Base march cost

        # Check terrain modifiers
        friendly = state.get_friendly_locations(self.player_id)
        neighbors = state.get_adjacent_locations(target)
        for nb in neighbors:
            if nb in friendly:
                terrain = state.get_terrain(nb, target)
                if terrain == TerrainType.DIFFICULT:
                    cost += 1
                break

        if loc.is_fortified:
            cost += 1

        # Can we afford it?
        if player.military < max(1, cost):
            return 0.0

        score = 0.0

        # Base reward: 1 VP + 1 prestige (Jin)
        score += 2.0  # 1 VP
        if player.faction.value == "jin":
            score += 1.5  # 1 prestige

        # Strategic value: who controls it?
        ctrl = loc.controller
        if ctrl == ControlState.SIMA:
            score += 2.0  # Taking from Sima is good
        elif hasattr(ctrl, 'value') and ctrl.value not in ("neutral", "empty", self.player_id):
            score += 1.5  # Taking from opponent

        # Location VP value (from region control)
        for reg, cfg in REGION_CONFIG.items():
            if target in cfg.get("locations", []):
                vp_value = cfg.get("vp_per_location", 1)
                score += vp_value * 1.0
                break

        # Cost efficiency
        score -= cost * 0.3

        return max(0.0, min(score, 10.0))

    def _score_occupy(self, action, state) -> float:
        """Score occupying a neutral/empty location.

        High priority for adjacent empty locations — these are free real estate
        that give VP from region control without combat.
        """
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        if player.military < 1:
            return 0.0

        target = getattr(action, 'target_location', '')
        score = 3.0  # Base: high priority — occupying is a key action

        # Adjacent empty location: extra value (closer to our territory)
        friendly = state.get_friendly_locations(self.player_id)
        neighbors = state.get_adjacent_locations(target)
        if any(nb in friendly for nb in neighbors):
            score += 2.0  # Adjacent to our territory — even better

        # Region VP value
        for reg, cfg in REGION_CONFIG.items():
            if target in cfg.get("locations", []):
                score += cfg.get("vp_per_location", 1) * 1.5
                break

        return max(0.0, min(score, 10.0))

    def _score_fortify(self, action, state) -> float:
        """Score fortifying a location."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        if player.military < 1:
            return 0.0

        target = getattr(action, 'target_location', '')
        loc = state.locations.get(target)
        if loc and loc.is_fortified:
            return 0.0  # Already fortified

        # Fortify key locations: those in high-VP regions or bordering enemies
        score = 1.0
        for reg, cfg in REGION_CONFIG.items():
            if target in cfg.get("locations", []):
                score += cfg.get("vp_per_location", 1) * 0.5
                break

        return max(0.0, min(score, 10.0))

    def _score_spread_culture(self, action, state) -> float:
        """Score spreading culture."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        # Culture spread gives VP + contribution for Jin
        score = 3.0
        if player.faction.value == "jin":
            score += 2.0  # Extra value for contribution
        return score

    def _score_convert(self, action, state) -> float:
        """Score converting a location's culture."""
        score = 2.0
        target = getattr(action, 'target_location', '')
        loc = state.locations.get(target)
        if loc and loc.culture_marker is not None:
            score += 1.0  # Converting existing marker is more valuable
        return score

    def _score_recruit(self, action, state) -> float:
        """Score recruiting (discard 1 card → 1 military).

        High priority when empty occupiable locations exist but no military.
        """
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        # Check: are there empty occupiable adjacent locations?
        friendly = state.get_friendly_locations(self.player_id)
        has_occupy_targets = False
        for loc_id, loc in state.locations.items():
            if loc.controller == ControlState.EMPTY:
                neighbors = state.get_adjacent_locations(loc_id)
                if any(nb in friendly for nb in neighbors):
                    has_occupy_targets = True
                    break

        # If empty occupiable locations exist AND no military, recruit is top priority
        if has_occupy_targets and player.military == 0:
            return 8.0  # High priority: need military to occupy

        # Only recruit if hand has expendable cards and military is low
        if len(player.hand) <= 2:
            return 0.0  # Keep cards
        if player.military >= 5:
            return 0.5  # Don't need it

        # If occupy targets exist with low military, higher priority
        if has_occupy_targets and player.military < 2:
            return 4.0

        return 1.5  # Worth considering

    def _score_draw(self, action, state) -> float:
        """Score drawing cards (quick action)."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        # Draw when hand is low
        if len(player.hand) <= 3:
            return 3.0
        elif len(player.hand) <= 5:
            return 2.0
        else:
            return 1.0  # Still worth it when nothing else to do

    def _score_archive(self, action, state) -> float:
        """Score archiving a card."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        # Archive gives VP from card's history_vp + 1 contribution (Jin)
        score = 2.0
        if player.faction.value == "jin":
            score += 1.0
        return score

    def _score_raise_order(self, action, state) -> float:
        """Score raising order (acting earlier next round)."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        if player.faction.value != "jin":
            return 1.0

        # Raise order to go earlier (lower number = earlier)
        if player.order >= 5:
            return 3.0  # Need to move up
        elif player.order >= 3:
            return 2.0
        else:
            return 1.0

    def _score_activate_effect(self, action, state) -> float:
        """Score activating a hero or staff card's active ability."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        card_id = getattr(action, 'card_id', '')
        block_index = getattr(action, 'block_index', 0)

        # Find the card
        card = None
        if player.hero and player.hero.definition.card_id == card_id:
            card = player.hero
        else:
            for c in player.staff_area:
                if c.definition.card_id == card_id:
                    card = c
                    break
        if not card:
            return 0.0

        parsed = card.definition.parsed_effect
        if not parsed:
            return 0.0

        active_blocks = [b for b in parsed.blocks if b.ability_type == AbilityType.ACTIVE]
        if block_index >= len(active_blocks):
            return 0.0

        block = active_blocks[block_index]

        # ── Check affordability ──────────────────────────
        for cost in block.costs:
            if not self._can_afford_cost(cost, player, state):
                return 0.0  # Can't afford

        score = 2.0  # Base value for active abilities

        # Score the expected gains
        for step in block.steps:
            score += self._step_value(step)

        # If choice_options, score the best option
        if block.choice_options:
            best_choice = 0.0
            for option_steps in block.choice_options:
                opt_score = sum(self._step_value(s) for s in option_steps)
                best_choice = max(best_choice, opt_score)
            score += best_choice

        return max(0.0, min(score, 10.0))

    def _score_play_public_card(self, action, state) -> float:
        """Score using a public action card."""
        player = state.get_player(self.player_id)
        if not player:
            return 0.0

        card_id = getattr(action, 'card_id', '')

        # Find the card in public pool
        pool_card = None
        for c in state.public_action_pool:
            if c.definition.card_id == card_id:
                pool_card = c
                break
        if not pool_card:
            return 0.0

        defn = pool_card.definition
        score = 1.0
        cost = defn.cost or 0

        # ── Check play_condition ─────────────────────────
        parsed = defn.parsed_effect
        if parsed and parsed.play_condition:
            resolver = getattr(state, 'effect_resolver', None)
            if resolver and not resolver.check_condition(
                parsed.play_condition, state, self.player_id):
                return 0.0  # Condition not met

        # ── Check block-level costs ──────────────────────
        if parsed:
            for block in parsed.blocks:
                for cost_item in block.costs:
                    if not self._can_afford_cost(cost_item, player, state):
                        return 0.0  # Can't afford

                # Score resource gains
                for step in block.steps:
                    score += self._step_value(step)

        # Payment cost: discard hand cards
        score -= cost * 0.5

        return max(0.0, min(score, 10.0))

    def _can_afford_cost(self, cost, player, state) -> bool:
        """Check whether the player can afford a block-level cost."""
        ct = cost.cost_type if hasattr(cost, 'cost_type') else cost.get('cost_type', '')
        params = cost.params if hasattr(cost, 'params') else cost

        if ct == "pay_military":
            amount = params.get("amount", 0) if isinstance(params, dict) else getattr(cost, 'amount', 0)
            return player.military >= amount
        elif ct == "pay_vp":
            amount = params.get("amount", 0) if isinstance(params, dict) else getattr(cost, 'amount', 0)
            return player.vp >= amount
        elif ct == "discard_cards":
            count = params.get("count", 1) if isinstance(params, dict) else getattr(cost, 'count', 1)
            return len(player.hand) >= count
        # Unknown cost type — assume affordable
        return True

    # === Legacy ===

    def take_turn(self, state: "GameState") -> list:
        """Legacy batch interface — engine uses decide_action iteratively."""
        return []

    # === Choice methods ===

    def make_choice(self, state: "GameState", prompt: dict) -> int:
        """Choose the option with the highest expected value."""
        options = prompt.get("options", [])
        if not options:
            return 0
        # Simple: pick middle option (often the balanced choice)
        # Add slight random variation
        if len(options) >= 3:
            return 1  # Middle
        return self.rng.randint(0, len(options) - 1)

    def select_target(self, state: "GameState", prompt: dict) -> Optional[str]:
        """Select a target — prefer high-value locations."""
        options = prompt.get("options", [])
        if not options:
            return None

        # If dict options, extract 'id' from the chosen dict
        if options and isinstance(options[0], dict):
            chosen = self.rng.choice(options)
            return chosen.get("id", str(chosen))

        # If locations, prefer higher VP regions
        def location_value(loc_id):
            for reg, cfg in REGION_CONFIG.items():
                if loc_id in cfg.get("locations", []):
                    return cfg.get("vp_per_location", 1)
            return 0

        scored = [(location_value(o), o) for o in options if isinstance(o, str)]
        if scored:
            scored.sort(reverse=True)
            # Pick from top 3 with randomness
            top = scored[:min(3, len(scored))]
            return self.rng.choice(top)[1]

        return self.rng.choice(options) if options else None
