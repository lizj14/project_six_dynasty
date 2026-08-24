"""测试 Effect Resolver — 所有核心 effect_type 的状态变更。

每个 test 验证操作符对 GameState 的实际效果。
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import (
    FactionType, CardType, CultureType, ControlState,
)
from models.card import CardDef, Card
from models.player import PlayerState
from models.location import LocationState
from models.game_state import GameState, CultureTrackState
from cards.effect_ast import (
    EffectStep, AbilityBlock, CardEffect, Condition, Cost,
    AbilityType, EffectType,
)
from cards.effect_resolver import EffectResolver


@pytest.fixture
def resolver():
    return EffectResolver()


def _card_def(card_id="test", history_vp=0):
    """Convenience: minimal CardDef."""
    return CardDef(
        card_id=card_id, name="测试卡", owner_faction="初始",
        cost=0, card_type=CardType.STRATEGY,
        card_category=CardType.STRATEGY, effect_text="测试",
        history_vp=history_vp,
    )


def _mk_step(effect_type, params=None, condition=None):
    return EffectStep(effect_type=effect_type, params=params or {}, condition=condition)


# ============================================================
# Resource changes
# ============================================================

class TestGainMilitary:
    def test_gain(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        old = player.military
        step = _mk_step("gain_military", {"amount": 3})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert player.military == old + 3

    def test_gain_zero(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        old = player.military
        step = _mk_step("gain_military", {"amount": 0})
        resolver._execute_step(step, minimal_state, "north")
        assert player.military == old


class TestGainVP:
    def test_gain(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        old = player.vp
        step = _mk_step("gain_vp", {"amount": 5})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert player.vp == old + 5

    def test_fires_trigger(self, minimal_state, resolver):
        fired = []
        resolver.trigger_callback = lambda tt, ctx: fired.append(tt)
        step = _mk_step("gain_vp", {"amount": 2})
        resolver._execute_step(step, minimal_state, "north")
        assert "on_gain_vp" in fired


class TestLoseVP:
    def test_lose(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.vp = 10
        step = _mk_step("lose_vp", {"amount": 3})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert player.vp == 7

    def test_floor_at_zero(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.vp = 2
        step = _mk_step("lose_vp", {"amount": 5})
        resolver._execute_step(step, minimal_state, "north")
        assert player.vp >= 0


class TestLoseMilitary:
    def test_lose(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.military = 8
        step = _mk_step("lose_military", {"amount": 3})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert player.military == 5


# ============================================================
# Cost payments
# ============================================================

class TestPayMilitary:
    def test_pay(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.military = 10
        step = _mk_step("pay_military", {"amount": 4})
        resolver._execute_step(step, minimal_state, "north")
        assert player.military == 6

    def test_insufficient_returns_error(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.military = 2
        step = _mk_step("pay_military", {"amount": 5})
        result = resolver._execute_step(step, minimal_state, "north")
        assert not result.success
        assert len(result.errors) > 0
        assert player.military == 2  # unchanged — payment rejected, not floored


class TestPayVP:
    def test_pay(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.vp = 10
        step = _mk_step("pay_vp", {"amount": 3})
        resolver._execute_step(step, minimal_state, "north")
        assert player.vp == 7


# ============================================================
# Card operations
# ============================================================

class TestDrawCards:
    def test_draw(self, minimal_state, resolver):
        # Fill deck with Card objects
        cards = [Card(definition=_card_def(f"deck_{i}")) for i in range(5)]
        minimal_state.main_deck = list(cards)
        player = minimal_state.get_player("north")
        old_hand = len(player.hand)
        step = _mk_step("draw_cards", {"count": 2})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert len(player.hand) == old_hand + 2

    def test_draw_from_empty_deck_no_crash(self, minimal_state, resolver):
        minimal_state.main_deck = []
        player = minimal_state.get_player("north")
        old_hand = len(player.hand)
        step = _mk_step("draw_cards", {"count": 3})
        result = resolver._execute_step(step, minimal_state, "north")
        assert len(player.hand) == old_hand  # No cards to draw


class TestDiscardCards:
    def test_discard(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=_card_def(f"h{i}")) for i in range(3)]
        step = _mk_step("discard_cards", {"count": 2})
        resolver._execute_step(step, minimal_state, "north")
        assert len(player.hand) == 1

    def test_fires_trigger(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=_card_def(f"h{i}")) for i in range(2)]
        fired = []
        resolver.trigger_callback = lambda tt, ctx: fired.append(tt)
        step = _mk_step("discard_cards", {"count": 1})
        resolver._execute_step(step, minimal_state, "north")
        assert "on_discard" in fired


class TestArchiveCard:
    def test_archive_from_hand(self, minimal_state, resolver):
        card_def = _card_def("archive_test", history_vp=2)
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=card_def)]
        old_vp = player.vp
        step = _mk_step("archive_card", {"from": "hand"})
        resolver._execute_step(step, minimal_state, "north")
        assert len(player.hand) == 0
        assert len(player.history_area) == 1
        assert player.vp == old_vp + 2  # history_vp added

    def test_archive_fires_trigger(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=_card_def("at"))]
        fired = []
        resolver.trigger_callback = lambda tt, ctx: fired.append(("trigger", tt))
        step = _mk_step("archive_card", {})
        resolver._execute_step(step, minimal_state, "north")
        assert any(t == "on_archive" for _, t in fired)


# ============================================================
# Track changes
# ============================================================

class TestRaiseOrder:
    def test_emits_request_without_action_system(self, minimal_state, resolver):
        """RaiseOrder requires action_system; without it, order unchanged."""
        player = minimal_state.get_player("jin_1")
        old = player.order
        step = _mk_step("raise_order", {"amount": 1})
        result = resolver._execute_step(step, minimal_state, "jin_1")
        assert result.success
        # Without action_system, the request is emitted but nothing happens
        assert player.order == old


class TestLowerOrder:
    def test_emits_request_without_action_system(self, minimal_state, resolver):
        player = minimal_state.get_player("jin_1")
        player.order = 5
        step = _mk_step("lower_order", {"amount": 2})
        result = resolver._execute_step(step, minimal_state, "jin_1")
        assert result.success
        # Without action_system, unchanged
        assert player.order == 5


class TestRaisePrestige:
    def test_raise(self, minimal_state, resolver):
        player = minimal_state.get_player("jin_1")
        old = player.prestige
        step = _mk_step("raise_prestige", {"amount": 2})
        result = resolver._execute_step(step, minimal_state, "jin_1")
        assert result.success
        assert player.prestige == min(9, old + 2)

    def test_fires_trigger(self, minimal_state, resolver):
        fired = []
        resolver.trigger_callback = lambda tt, ctx: fired.append(tt)
        step = _mk_step("raise_prestige", {"amount": 1})
        resolver._execute_step(step, minimal_state, "jin_1")
        assert "on_gain_prestige" in fired


class TestLowerPrestige:
    def test_lower(self, minimal_state, resolver):
        player = minimal_state.get_player("jin_1")
        player.prestige = 7
        step = _mk_step("lower_prestige", {"amount": 3})
        resolver._execute_step(step, minimal_state, "jin_1")
        assert player.prestige == 4


class TestRaiseContribution:
    def test_raise(self, minimal_state, resolver):
        player = minimal_state.get_player("jin_1")
        old = player.contribution
        step = _mk_step("raise_contribution", {"amount": 2})
        result = resolver._execute_step(step, minimal_state, "jin_1")
        assert result.success
        assert player.contribution == min(9, old + 2)

    def test_fires_trigger(self, minimal_state, resolver):
        fired = []
        # Wire resolver to state so add_contribution() can fire triggers
        minimal_state.effect_resolver = resolver
        resolver.trigger_callback = lambda tt, ctx: fired.append(tt)
        step = _mk_step("raise_contribution", {"amount": 1})
        resolver._execute_step(step, minimal_state, "jin_1")
        assert "on_gain_contribution" in fired


class TestLowerContribution:
    def test_lower(self, minimal_state, resolver):
        player = minimal_state.get_player("jin_1")
        player.contribution = 6
        step = _mk_step("lower_contribution", {"amount": 2})
        resolver._execute_step(step, minimal_state, "jin_1")
        assert player.contribution == 4


# ============================================================
# Culture
# ============================================================

class TestRaiseCultureLevel:
    def test_raise_player_contribution(self, minimal_state, resolver):
        """RaiseCultureLevel modifies player.culture_contributions, not state tracks."""
        player = minimal_state.get_player("north")
        player.culture_contributions[CultureType.CONFUCIANISM] = 1
        step = _mk_step("raise_culture_level", {"culture": "confucianism", "amount": 2})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert player.culture_contributions[CultureType.CONFUCIANISM] == 3


# ============================================================
# Markers / Tokens
# ============================================================

class TestGetExpedition:
    def test_get(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        assert not player.has_expedition_marker
        step = _mk_step("get_expedition")
        resolver._execute_step(step, minimal_state, "north")
        assert player.has_expedition_marker


class TestAddRefugee:
    def test_emits_event(self, minimal_state, resolver):
        """AddRefugee currently emits event but doesn't modify court (Phase 2a TODO)."""
        step = _mk_step("add_refugee", {"count": 2})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        # Currently just emits an event — not modifying state
        assert len(result.events) > 0


# ============================================================
# Map actions
# ============================================================

class TestPlaceArmy:
    def test_place(self, minimal_state, resolver):
        step = _mk_step("place_army", {"location": "弘农", "amount": 2})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        loc = minimal_state.locations["弘农"]
        assert loc.army_count == 2


class TestRemoveArmy:
    def test_remove(self, minimal_state, resolver):
        # Place army first, then remove
        loc = minimal_state.locations["弘农"]
        loc.army_count = 3
        step = _mk_step("remove_army", {"location": "弘农", "amount": 2})
        result = resolver._execute_step(step, minimal_state, "north")
        assert result.success
        assert loc.army_count == 1


# ============================================================
# Step conditions
# ============================================================

class TestStepCondition:
    def test_condition_met(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        old_vp = player.vp
        cond = Condition(condition_type="is_faction", params={"faction": "north"})
        step = _mk_step("gain_vp", {"amount": 3}, condition=cond)
        resolver._execute_step(step, minimal_state, "north")
        assert player.vp == old_vp + 3

    def test_condition_not_met_skips(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        old_vp = player.vp
        cond = Condition(condition_type="is_faction", params={"faction": "jin"})
        step = _mk_step("gain_vp", {"amount": 3}, condition=cond)
        resolver._execute_step(step, minimal_state, "north")
        assert player.vp == old_vp


# ============================================================
# Block resolution (strategy_action, choice, usurp)
# ============================================================

class TestBlockResolution:
    def test_strategy_action(self, minimal_state, resolver):
        block = AbilityBlock(
            ability_type=AbilityType.STRATEGY_ACTION,
            steps=[_mk_step("gain_military", {"amount": 3})],
        )
        player = minimal_state.get_player("north")
        old = player.military
        resolver._resolve_block(block, minimal_state, "north")
        assert player.military == old + 3

    def test_choice_first(self, minimal_state, resolver):
        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            choice_options=[
                [_mk_step("gain_vp", {"amount": 1})],
                [_mk_step("gain_military", {"amount": 2})],
            ],
        )
        player = minimal_state.get_player("north")
        old_vp = player.vp
        resolver._resolve_block(block, minimal_state, "north", {"choice_index": 0})
        assert player.vp == old_vp + 1

    def test_choice_second(self, minimal_state, resolver):
        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            choice_options=[
                [_mk_step("gain_vp", {"amount": 1})],
                [_mk_step("gain_military", {"amount": 2})],
            ],
        )
        player = minimal_state.get_player("north")
        old_mil = player.military
        resolver._resolve_block(block, minimal_state, "north", {"choice_index": 1})
        assert player.military == old_mil + 2

    def test_choice_strategy_action_with_pay_vp(self, minimal_state, resolver):
        """苏峻: 选择一项：支付3vp，然后获得5军力。choice must fire (not early-return)."""
        player = minimal_state.get_player("north")
        player.vp = 10
        player.military = 0
        block = AbilityBlock(
            ability_type=AbilityType.STRATEGY_ACTION,  # event choice cards parse as this
            steps=[],
            choice_options=[
                [_mk_step("pay_vp", {"amount": 3}),
                 _mk_step("gain_military", {"amount": 5})],
                [_mk_step("pay_military", {"amount": 3}), _mk_step("archive_this")],
            ],
        )
        resolver._resolve_block(block, minimal_state, "north", {"choice_index": 0})
        assert player.vp == 7          # 10 - 3
        assert player.military == 5    # 0 + 5

    def test_choice_insufficient_pay_vp_aborts(self, minimal_state, resolver):
        """支付3vp but only 1vp — option aborts, +5军力 must NOT apply."""
        player = minimal_state.get_player("north")
        player.vp = 1
        player.military = 0
        block = AbilityBlock(
            ability_type=AbilityType.STRATEGY_ACTION,
            steps=[],
            choice_options=[
                [_mk_step("pay_vp", {"amount": 3}),
                 _mk_step("gain_military", {"amount": 5})],
            ],
        )
        result = resolver._resolve_block(block, minimal_state, "north", {"choice_index": 0})
        assert not result.success
        assert len(result.errors) > 0
        assert player.vp == 1          # unchanged
        assert player.military == 0    # effect not applied

    def test_choice_asks_agent_when_no_index(self, minimal_state, resolver):
        """Event card (play_card) has no choice_index — resolver asks the agent."""
        player = minimal_state.get_player("north")
        player.vp = 10
        player.military = 0
        asked = []
        resolver.make_choice_callback = lambda pid, prompt: asked.append(prompt) or 1
        block = AbilityBlock(
            ability_type=AbilityType.STRATEGY_ACTION,
            steps=[],
            choice_options=[
                [_mk_step("gain_vp", {"amount": 3})],
                [_mk_step("gain_military", {"amount": 5})],
            ],
        )
        resolver._resolve_block(block, minimal_state, "north")  # no choice_index
        assert len(asked) == 1
        assert asked[0]["type"] == "choose_effect"
        assert len(asked[0]["options"]) == 2
        assert player.military == 5    # option 1 executed
        assert player.vp == 10         # option 0 NOT executed

    def test_choice_defaults_to_zero_without_callback(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.vp = 10
        block = AbilityBlock(
            ability_type=AbilityType.STRATEGY_ACTION,
            steps=[],
            choice_options=[[_mk_step("gain_vp", {"amount": 3})]],
        )
        resolver._resolve_block(block, minimal_state, "north")  # no callback, no index
        assert player.vp == 13         # defaults to option 0

    def test_usurp_steps(self, minimal_state, resolver):
        """Jin player with highest prestige executes usurp_steps."""
        player = minimal_state.get_player("jin_1")
        player.prestige = 9
        minimal_state.get_player("jin_2").prestige = 1
        minimal_state.get_player("jin_3").prestige = 1
        minimal_state.sima.prestige = 0

        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            steps=[],
            usurp_steps=[_mk_step("gain_vp", {"amount": 5})],
        )
        old_vp = player.vp
        resolver._resolve_block(block, minimal_state, "jin_1")
        assert player.vp == old_vp + 5

    def test_block_costs_discard(self, minimal_state, resolver):
        """Block-level discard_cards cost."""
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=_card_def(f"c{i}")) for i in range(3)]
        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            costs=[Cost(cost_type="discard_cards", params={"count": 2})],
            steps=[_mk_step("gain_vp", {"amount": 1})],
        )
        resolver._resolve_block(block, minimal_state, "north")
        assert len(player.hand) == 1  # 3 - 2 discarded

    def test_block_costs_pay_military(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.military = 5
        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            costs=[Cost(cost_type="pay_military", params={"amount": 3})],
            steps=[],
        )
        resolver._resolve_block(block, minimal_state, "north")
        assert player.military == 2

    def test_block_costs_pay_vp(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.vp = 5
        block = AbilityBlock(
            ability_type=AbilityType.ACTIVE,
            costs=[Cost(cost_type="pay_vp", params={"amount": 2})],
            steps=[],
        )
        resolver._resolve_block(block, minimal_state, "north")
        assert player.vp == 3


# ============================================================
# Unknown effect_type
# ============================================================

class TestUnknownEffectType:
    def test_returns_error(self, minimal_state, resolver):
        step = _mk_step("nonexistent_effect_type_xyz")
        result = resolver._execute_step(step, minimal_state, "north")
        assert not result.success
        assert len(result.errors) > 0


# ============================================================
# OPERATOR_REGISTRY completeness
# ============================================================

class TestOperatorRegistry:
    EXPECTED = {
        "gain_military", "gain_vp", "lose_vp", "lose_military",
        "pay_military", "pay_vp",
        "draw_cards", "discard_cards", "archive_this", "archive_card",
        "archive_court", "search", "draft", "supply_court", "play_card",
        "march", "occupy", "convert", "fortify", "spread_culture",
        "raise_order", "lower_order",
        "raise_prestige", "lower_prestige",
        "raise_contribution", "lower_contribution",
        "raise_culture_level",
        "get_expedition", "add_refugee",
        "place_army", "remove_army", "remove_from_game",
        "choose", "conditional", "noop", "raw",
    }

    def test_all_expected_registered(self):
        from cards.effect_operators import OPERATOR_REGISTRY
        registered = set(OPERATOR_REGISTRY.keys())
        missing = self.EXPECTED - registered
        assert not missing, f"Missing effect_type operators: {missing}"

    def test_each_has_execute(self):
        from cards.effect_operators import OPERATOR_REGISTRY
        for et, op in OPERATOR_REGISTRY.items():
            assert hasattr(op, 'execute'), f"{et}: missing execute"
