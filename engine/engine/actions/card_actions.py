"""Card-based actions: play card from hand, execute strategy from court."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dataclasses import dataclass
from typing import Optional

from .base import GameAction, ActionResult
from models.enums import CardType, FactionType

@dataclass
class PlayCardAction(GameAction):
    """手牌行动：从手牌中选择一张打出。

    Different card types have different effects when played:
    - 幕僚牌: placed in staff area (max 3 Jin / 4 North)
    - 事件牌: effect resolved, then discarded to main discard
    - 策略牌: placed on top of national deck

    Cost: card's cost (0-3) — paid by discarding other cards from hand.
    """
    action_type: str = "play_card"
    player_id: str = ""
    card_index: int = -1                      # Index in hand
    payment_indices: list[int] = None         # Indices of cards to discard as payment
    replace_staff_index: int = 0              # Which staff card to replace if staff full

    def __post_init__(self):
        if self.payment_indices is None:
            self.payment_indices = []

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if not player.can_take_hand_action():
            return ActionResult.fail("Already used hand action this turn")

        if self.card_index < 0 or self.card_index >= len(player.hand):
            return ActionResult.fail(f"Invalid card index {self.card_index}")

        card = player.hand[self.card_index]

        # Check payment
        cost = card.cost
        if len(self.payment_indices) != cost:
            return ActionResult.fail(f"Need to pay {cost} cards as cost, "
                                     f"provided {len(self.payment_indices)}")

        # Validate payment indices
        used_indices = {self.card_index}
        for pi in self.payment_indices:
            if pi < 0 or pi >= len(player.hand):
                return ActionResult.fail(f"Invalid payment index {pi}")
            if pi in used_indices:
                return ActionResult.fail(f"Duplicate index {pi} in payment")
            used_indices.add(pi)

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)

        # Pay cost first — discard payment cards (in reverse index order)
        payment_cards = []
        for pi in sorted(self.payment_indices, reverse=True):
            payment_cards.append(player.hand.pop(pi))

        # Get the played card (index may have shifted due to payments)
        # Recalculate: find the card by original index accounting for removals
        adjusted_index = self.card_index
        for pi in sorted(self.payment_indices, reverse=True):
            if pi < self.card_index:
                adjusted_index -= 1
        card = player.hand.pop(adjusted_index)

        # Discard payment cards to main discard
        state.main_discard.extend(payment_cards)

        events = [{"type": "play_card", "player": self.player_id,
                    "card": card.name, "cost_paid": len(payment_cards),
                    "payment_cards": [c.name for c in payment_cards]}]

        # === Faction restriction check ===
        # Card cannot be played by this faction → discard (no effect, cost already paid).
        # This is the unified path for both normal play (safety net — agents never
        # select restricted cards) and setup (cards pre-assigned may not match faction).
        if not card.definition.is_playable_by(player.faction):
            state.main_discard.append(card)
            events.append({"type": "card_discarded", "card": card.name,
                           "reason": "faction_restriction"})
            player.hand_action_taken_count += 1
            player.has_taken_hand_action = True
            state.log_event("play_card_failed", player=self.player_id,
                           card=card.name, reason="faction_restriction")
            return ActionResult.ok(events)

        # === Play condition check (all card types) ===
        # Card's play_condition not met → discard (no effect, cost already paid).
        # Applies to EVENT, STRATEGY, and FRIEND cards alike — e.g. 凉州大马
        # requires 控制[西凉] and is a STRATEGY card.
        if card.card_type != CardType.HERO:
            parsed = card.definition.parsed_effect
            if parsed and parsed.play_condition:
                resolver = getattr(state, 'effect_resolver', None)
                if resolver and not resolver.check_condition(
                    parsed.play_condition, state, self.player_id):
                    state.main_discard.append(card)
                    events.append({"type": "card_discarded", "card": card.name,
                                   "reason": "condition_not_met"})
                    player.hand_action_taken_count += 1
                    player.has_taken_hand_action = True
                    state.log_event("play_card_failed", player=self.player_id,
                                   card=card.name, reason="condition_not_met")
                    return ActionResult.ok(events)

        # Handle card by type
        if card.is_friend:
            # 幕僚牌 — place in staff area
            # If staff area is full, replace the staff member at replace_staff_index
            if not player.can_play_friend():
                if 0 <= self.replace_staff_index < len(player.staff_area):
                    replaced = player.staff_area.pop(self.replace_staff_index)
                    state.main_discard.append(replaced)
                    events.append({"type": "staff_replaced",
                                   "card": replaced.name,
                                   "replaced_by": card.name,
                                   "index": self.replace_staff_index})
            player.staff_area.append(card)
            events.append({"type": "friend_played", "card": card.name})

            # Note: enter effects handled by resolver below

        elif card.card_type == CardType.EVENT:
            # 事件牌 — resolve effect, then discard to main discard
            state.main_discard.append(card)
            events.append({"type": "event_played", "card": card.name})

        elif card.card_type == CardType.STRATEGY:
            # 策略牌 — place on top of national deck
            national_deck = state.get_national_deck(self.player_id)
            national_deck.insert(0, card)
            events.append({"type": "strategy_played", "card": card.name,
                           "added_to": f"{self.player_id}_deck"})

            # Jin players: reform (改革) grants VP = card cost + 1,
            # plus 1 contribution for adding strategy to deck
            if player.faction == FactionType.JIN:
                reform_vp = card.cost + 1
                player.vp += reform_vp
                events.append({"type": "reform_vp", "vp": reform_vp, "card_cost": card.cost})
                player.contribution = min(9, player.contribution + 1)
                events.append({"type": "contribution_gained", "amount": 1})

        # === Resolve card effects via EffectResolver ===
        # Strategy cards go to deck; effects fire later via CourtAction.
        # Friend and event cards fire effects immediately on play.
        # Active ability blocks are excluded — they must be activated
        # explicitly via ActivateEffectAction during the player's turn.
        if card.card_type in (CardType.FRIEND, CardType.EVENT):
            parsed = card.definition.parsed_effect
            resolver = getattr(state, 'effect_resolver', None)
            if resolver and parsed:
                effect_result = resolver.resolve(
                    parsed, state, self.player_id,
                    context={"source": "play_card", "card_id": card.definition.card_id},
                    exclude_ability_types={"active"},
                )
                events.extend(effect_result.events)
                if effect_result.errors:
                    events.append({"type": "effect_errors", "errors": effect_result.errors})

        player.hand_action_taken_count += 1
        player.has_taken_hand_action = True
        state.log_event("play_card", player=self.player_id, card=card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        if self.card_index < 0 or self.card_index >= len(state.get_player(self.player_id).hand):
            return "?"
        card = state.get_player(self.player_id).hand[self.card_index]
        return f"支付{card.cost}张手牌"


@dataclass
class PublicCardAction(GameAction):
    """公共行动牌：使用共享公共行动牌池中的一张牌，消耗手牌行动次数。

    Similar to PlayCardAction + CourtAction combined:
    - Counts as the player's hand action for the turn
    - Pays the card's cost from hand (like PlayCardAction)
    - Resolves strategy_action effect (like CourtAction)
    - Card flips face-down (exhausted) instead of being discarded
    - All 5 cards recover at the start of each round
    """
    action_type: str = "play_public_card"
    player_id: str = ""
    card_id: str = ""                         # card_id of the public card
    payment_indices: list[int] = None         # Indices of hand cards to discard as payment

    def __post_init__(self):
        if self.payment_indices is None:
            self.payment_indices = []

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if not player.can_take_hand_action():
            return ActionResult.fail("Already used hand action this turn")

        # Find card in public pool
        pool_card = None
        for c in state.public_action_pool:
            if c.definition.card_id == self.card_id:
                pool_card = c
                break
        if not pool_card:
            return ActionResult.fail(f"Public card {self.card_id} not in pool")

        if self.card_id in state.public_exhausted:
            return ActionResult.fail(f"Public card {pool_card.name} is exhausted this round")

        # Check faction restriction
        if not pool_card.definition.is_playable_by(player.faction):
            return ActionResult.fail(
                f"Cannot use {pool_card.name} — faction restricted")

        # Check payment
        cost = pool_card.cost
        if len(self.payment_indices) != cost:
            return ActionResult.fail(f"Need to pay {cost} cards as cost, "
                                     f"provided {len(self.payment_indices)}")

        # Validate payment indices
        used_indices = set()
        for pi in self.payment_indices:
            if pi < 0 or pi >= len(player.hand):
                return ActionResult.fail(f"Invalid payment index {pi}")
            if pi in used_indices:
                return ActionResult.fail(f"Duplicate index {pi} in payment")
            used_indices.add(pi)

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)

        # Find card in public pool
        pool_card = None
        for c in state.public_action_pool:
            if c.definition.card_id == self.card_id:
                pool_card = c
                break
        if not pool_card:
            return ActionResult.fail("Public card not found in pool")

        # Pay cost from hand
        payment_cards = []
        for pi in sorted(self.payment_indices, reverse=True):
            payment_cards.append(player.hand.pop(pi))
        state.main_discard.extend(payment_cards)

        events = [{"type": "play_public_card", "player": self.player_id,
                    "card": pool_card.name, "cost_paid": len(payment_cards),
                    "payment_cards": [c.name for c in payment_cards]}]

        # Mark card as exhausted (flip face-down for this round)
        state.public_exhausted.add(self.card_id)
        events.append({"type": "public_card_exhausted", "card": pool_card.name})

        # Resolve the card's strategy_action effect via EffectResolver
        defn = pool_card.definition
        parsed = defn.parsed_effect
        resolver = getattr(state, 'effect_resolver', None)
        if resolver and parsed:
            effect_result = resolver.resolve(
                parsed, state, self.player_id,
                context={"source": "play_public_card", "card_id": defn.card_id},
            )
            events.extend(effect_result.events)
            if effect_result.errors:
                events.append({"type": "effect_errors", "errors": effect_result.errors})

        # Check end condition: VP >= 150
        if state.check_vp_game_end(self.player_id):
            events.append({"type": "game_end_trigger", "reason": "150vp",
                           "player": self.player_id})

        player.hand_action_taken_count += 1
        player.has_taken_hand_action = True
        state.log_event("play_public_card", player=self.player_id,
                        card=pool_card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        pool_card = None
        for c in state.public_action_pool:
            if c.definition.card_id == self.card_id:
                pool_card = c
                break
        if not pool_card:
            return "?"
        return f"支付{pool_card.cost}张手牌"


@dataclass
class CourtAction(GameAction):
    """牌组行动：从朝堂区选择一张候选策略牌，结算行动效果。

    The strategy card's action effect is resolved, then the card
    moves to the national board's "played this round" area.
    """
    action_type: str = "court_action"
    player_id: str = ""
    card_id: str = ""             # card_id of the strategy card in court

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if not player.can_take_court_action():
            return ActionResult.fail("Already used court action this turn")

        court = state.get_court_cards(self.player_id)
        if not any(c.definition.card_id == self.card_id for c in court):
            return ActionResult.fail(f"Card {self.card_id} not in court")

        # Check if card is playable by this faction
        target_card = next(c for c in court if c.definition.card_id == self.card_id)
        if not target_card.definition.is_playable_by(player.faction):
            return ActionResult.fail(f"Cannot execute {target_card.name} — faction restricted")

        # Card must have a court action effect in its AST
        if not target_card.definition.has_strategy_action:
            return ActionResult.fail(f"{target_card.name} has no court action effect")

        return ActionResult.ok()

    def execute(self, state: "GameState") -> ActionResult:
        validation = self.validate(state)
        if not validation.success:
            return validation

        player = state.get_player(self.player_id)
        court = state.get_court_cards(self.player_id)

        # Find and remove card from court
        card = None
        for i, c in enumerate(court):
            if c.definition.card_id == self.card_id:
                card = court.pop(i)
                break

        if not card:
            return ActionResult.fail("Card not found in court")

        # Move to played-this-round area
        if self.player_id == "north":
            state.north_played_this_round.append(card)
        else:
            state.jin_played_this_round.append(card)

        events = [{"type": "court_action", "player": self.player_id,
                    "card": card.name}]

        # Resolve card effects via EffectResolver
        defn = card.definition
        parsed = defn.parsed_effect
        resolver = getattr(state, 'effect_resolver', None)
        if resolver and parsed:
            effect_result = resolver.resolve(
                parsed, state, self.player_id,
                context={"source": "court_action", "card_id": defn.card_id},
            )
            events.extend(effect_result.events)
            if effect_result.errors:
                events.append({"type": "effect_errors", "errors": effect_result.errors})
        else:
            # Fallback: no resolver or no parsed effect — use resource values directly
            if defn.resource_military > 0:
                player.military += defn.resource_military
                events.append({"type": "court_military",
                               "amount": defn.resource_military})
            if defn.resource_vp > 0:
                player.vp += defn.resource_vp
                events.append({"type": "court_vp", "amount": defn.resource_vp})

        # Check end condition: VP >= 150
        if state.check_vp_game_end(self.player_id):
            events.append({"type": "game_end_trigger", "reason": "150vp",
                           "player": self.player_id})

        player.has_taken_court_action = True
        player.court_action_taken_count += 1
        state.log_event("court_action", player=self.player_id, card=card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "牌组行动（每回合1次）"
