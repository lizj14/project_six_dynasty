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

    def __post_init__(self):
        if self.payment_indices is None:
            self.payment_indices = []

    def validate(self, state: "GameState") -> ActionResult:
        player = state.get_player(self.player_id)
        if not player:
            return ActionResult.fail(f"Player {self.player_id} not found")

        if player.has_taken_hand_action:
            return ActionResult.fail("Already used hand action this turn")

        if self.card_index < 0 or self.card_index >= len(player.hand):
            return ActionResult.fail(f"Invalid card index {self.card_index}")

        card = player.hand[self.card_index]

        # Check faction restriction
        if not card.definition.is_playable_by(player.faction):
            return ActionResult.fail(f"Cannot play {card.name} — faction restricted")

        # Check friend limit
        if card.is_friend and not player.can_play_friend():
            return ActionResult.fail(f"Staff area full (limit: {player.staff_limit})")

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
                    "card": card.name, "cost_paid": len(payment_cards)}]

        # Handle card by type
        if card.is_friend:
            # 幕僚牌 — place in staff area
            # If staff area full, must replace (handled in validate)
            player.staff_area.append(card)
            events.append({"type": "friend_played", "card": card.name})

            # Trigger enter effects (handled by effect resolver later)

        elif card.card_type == CardType.EVENT:
            # 事件牌 — resolve effect, then discard to main discard
            # Effect resolution will be handled by the effect resolver
            state.main_discard.append(card)
            events.append({"type": "event_played", "card": card.name})

        elif card.card_type == CardType.STRATEGY:
            # 策略牌 — place on top of national deck
            national_deck = state.get_national_deck(self.player_id)
            national_deck.insert(0, card)
            events.append({"type": "strategy_played", "card": card.name,
                           "added_to": f"{self.player_id}_deck"})

            # Jin players: gain 1 contribution for adding strategy to deck
            if player.faction == FactionType.JIN:
                player.contribution = min(9, player.contribution + 1)
                events.append({"type": "contribution_gained", "amount": 1})

        player.has_taken_hand_action = True
        state.log_event("play_card", player=self.player_id, card=card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        if self.card_index < 0 or self.card_index >= len(state.get_player(self.player_id).hand):
            return "?"
        card = state.get_player(self.player_id).hand[self.card_index]
        return f"支付{card.cost}张手牌"

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

        if player.has_taken_court_action:
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

        # Strategy action effect: use pre-parsed AST (no runtime parsing)
        defn = card.definition
        parsed = defn.parsed_effect

        from cards.effect_ast import AbilityType, EffectType
        strategy_block = None
        if parsed:
            for block in parsed.blocks:
                if block.ability_type == AbilityType.STRATEGY_ACTION:
                    strategy_block = block
                    break

        if strategy_block:
            # Pay block-level costs first
            for cost in strategy_block.costs:
                if cost.cost_type == "discard_cards":
                    count = cost.params.get("count", 1)
                    for _ in range(count):
                        if player.hand:
                            state.main_discard.append(player.hand.pop())
                elif cost.cost_type == "pay_military":
                    player.military = max(0, player.military - cost.params.get("amount", 0))
                elif cost.cost_type == "pay_vp":
                    player.vp = max(0, player.vp - cost.params.get("amount", 0))

            # Then execute steps
            for step in strategy_block.steps:
                if step.effect_type == EffectType.GAIN_MILITARY:
                    amt = step.params.get("amount", 0)
                    if isinstance(amt, int):
                        player.military += amt
                    events.append({"type": "court_military", "amount": amt,
                                   "raw": step.source_text})
                elif step.effect_type == EffectType.GAIN_VP:
                    amt = step.params.get("amount", 0)
                    if isinstance(amt, int):
                        player.vp += amt
                    events.append({"type": "court_vp", "amount": amt,
                                   "raw": step.source_text})
                elif step.effect_type == EffectType.DRAW_CARDS:
                    count = step.params.get("count", 1)
                    for _ in range(count):
                        if state.main_deck:
                            drawn = state.main_deck.pop(0)
                            player.hand.append(drawn)
                    events.append({"type": "court_draw", "count": count})
                else:
                    events.append({"type": "court_effect_unhandled",
                                   "effect": step.effect_type,
                                   "raw": step.source_text})
        else:
            # Fallback: no parsed action block — use resource values directly
            if defn.resource_military > 0:
                player.military += defn.resource_military
                events.append({"type": "court_military",
                               "amount": defn.resource_military})
            if defn.resource_vp > 0:
                player.vp += defn.resource_vp
                events.append({"type": "court_vp", "amount": defn.resource_vp})

        # Check end condition: VP >= 150
        if player.vp >= 150:
            state.game_end_marker = self.player_id
            state.game_end_reason = "150vp"
            events.append({"type": "game_end_trigger", "reason": "150vp",
                           "player": self.player_id})

        player.has_taken_court_action = True
        state.log_event("court_action", player=self.player_id, card=card.name)
        return ActionResult.ok(events)

    def cost_description(self, state: "GameState") -> str:
        return "牌组行动（每回合1次）"
