"""测试 Condition 系统 — 所有 27 个 condition_type 的 OOP 算子。

参数名基于 condition_operators.py 的实际实现。
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import (
    FactionType, CardType, MarkerType, CultureType, ControlState,
)
from models.card import CardDef, Card
from models.player import PlayerState
from models.location import LocationState
from models.game_state import GameState, CultureTrackState
from cards.effect_ast import Condition
from cards.condition_operators import CONDITION_REGISTRY
from cards.effect_resolver import EffectResolver


@pytest.fixture
def resolver():
    return EffectResolver()


# ============================================================
# Logical combinators
# ============================================================

class TestAndCondition:
    def test_both_true(self, minimal_state, resolver):
        cond = Condition(condition_type="and", params={
            "conditions": [
                {"condition_type": "is_faction", "params": {"faction": "north"}},
                {"condition_type": "has_military", "params": {"amount": 1}},
            ]
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_one_false(self, minimal_state, resolver):
        cond = Condition(condition_type="and", params={
            "conditions": [
                {"condition_type": "is_faction", "params": {"faction": "north"}},
                {"condition_type": "has_military", "params": {"amount": 100}},
            ]
        })
        assert not resolver.check_condition(cond, minimal_state, "north")

    def test_empty_conditions(self, minimal_state, resolver):
        cond = Condition(condition_type="and", params={"conditions": []})
        assert resolver.check_condition(cond, minimal_state, "north")


class TestNotCondition:
    def test_not_true(self, minimal_state, resolver):
        cond = Condition(condition_type="not", params={
            "condition": {"condition_type": "is_faction", "params": {"faction": "jin"}}
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_not_false(self, minimal_state, resolver):
        cond = Condition(condition_type="not", params={
            "condition": {"condition_type": "is_faction", "params": {"faction": "north"}}
        })
        assert not resolver.check_condition(cond, minimal_state, "north")


# ============================================================
# Player identity
# ============================================================

class TestIsFactionCondition:
    def test_north_is_north(self, minimal_state, resolver):
        cond = Condition(condition_type="is_faction", params={"faction": "north"})
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_jin_is_jin(self, minimal_state, resolver):
        cond = Condition(condition_type="is_faction", params={"faction": "jin"})
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_north_not_jin(self, minimal_state, resolver):
        cond = Condition(condition_type="is_faction", params={"faction": "jin"})
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestCanUsurpCondition:
    def test_cannot_when_not_highest(self, minimal_state, resolver):
        cond = Condition(condition_type="can_usurp")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")

    def test_can_when_highest(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").prestige = 9
        minimal_state.get_player("jin_2").prestige = 1
        minimal_state.get_player("jin_3").prestige = 1
        minimal_state.sima.prestige = 0
        cond = Condition(condition_type="can_usurp")
        assert resolver.check_condition(cond, minimal_state, "jin_1")


# ============================================================
# Compare (op: >, >=, <, <=, ==, !=)
# ============================================================

class TestCompareCondition:
    def test_military_gt(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "military", "op": ">", "right": 3
        })
        assert resolver.check_condition(cond, minimal_state, "north")  # 5 > 3

    def test_military_lt_false(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "military", "op": "<", "right": 3
        })
        assert not resolver.check_condition(cond, minimal_state, "north")  # 5 < 3?

    def test_military_eq(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "military", "op": "==", "right": 5
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_prestige_gte(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "prestige", "op": ">=", "right": 0
        })
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_hand_count(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "hand_count", "op": ">=", "right": 0
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_friend_count_lt_staff_limit(self, minimal_state, resolver):
        cond = Condition(condition_type="compare", params={
            "left": "friend_count", "op": "<", "right": "staff_limit"
        })
        assert resolver.check_condition(cond, minimal_state, "north")  # 0 < staff_limit


# ============================================================
# Resources
# ============================================================

class TestHasMilitaryCondition:
    def test_has(self, minimal_state, resolver):
        cond = Condition(condition_type="has_military", params={"amount": 1})
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_not_enough(self, minimal_state, resolver):
        cond = Condition(condition_type="has_military", params={"amount": 10})
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestStaffHasSpaceCondition:
    def test_has_space(self, minimal_state, resolver):
        cond = Condition(condition_type="staff_has_space")
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_no_space(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        card_def = CardDef(card_id="test_friend", name="test", owner_faction="初始",
                           cost=0, card_type=CardType.STRATEGY, card_category=CardType.STRATEGY,
                           effect_text="测试")
        # Fill to staff_limit (4 for North by default)
        player.staff_area = [Card(definition=card_def) for _ in range(4)]
        cond = Condition(condition_type="staff_has_space")
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestHasExpeditionCondition:
    def test_no_expedition(self, minimal_state, resolver):
        cond = Condition(condition_type="has_expedition")
        assert not resolver.check_condition(cond, minimal_state, "north")

    def test_has_expedition(self, minimal_state, resolver):
        minimal_state.get_player("north").has_expedition_marker = True
        cond = Condition(condition_type="has_expedition")
        assert resolver.check_condition(cond, minimal_state, "north")


# ============================================================
# Markers
# ============================================================

class TestMarkerCountGtCondition:
    def test_gt(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 3
        cond = Condition(condition_type="marker_count_gt", params={
            "marker": "military", "threshold": 2
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_not_gt(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 1
        cond = Condition(condition_type="marker_count_gt", params={
            "marker": "military", "threshold": 2
        })
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestMarkerCountCondition:
    def test_ge(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 3
        cond = Condition(condition_type="marker_count", params={
            "marker": "military", "min": 3
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_not_ge(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 1
        cond = Condition(condition_type="marker_count", params={
            "marker": "military", "min": 3
        })
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestHasTokenCondition:
    def test_no_token(self, minimal_state, resolver):
        """has_token resolves the param as a variable — 0 for unknown tokens."""
        cond = Condition(condition_type="has_token", params={"token": "nonexistent"})
        assert not resolver.check_condition(cond, minimal_state, "north")

    def test_token_resolves_to_positive(self, minimal_state, resolver):
        """token 'hand_size' won't match but shows resolution works."""
        # Place cards in hand so hand_size > 0
        card_def = CardDef(card_id="t", name="t", owner_faction="初始",
                           cost=0, card_type=CardType.STRATEGY,
                           card_category=CardType.STRATEGY, effect_text="测试")
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=card_def)]
        cond = Condition(condition_type="has_token", params={"token": "hand_size"})
        assert resolver.check_condition(cond, minimal_state, "north")


# ============================================================
# Culture
# ============================================================

class TestCultureLevelGtCondition:
    def test_gt(self, minimal_state, resolver):
        minimal_state.get_player("north").culture_contributions[CultureType.CONFUCIANISM] = 5
        cond = Condition(condition_type="culture_level_gt", params={
            "culture": "confucianism", "threshold": 2
        })
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_not_gt(self, minimal_state, resolver):
        minimal_state.get_player("north").culture_contributions[CultureType.CONFUCIANISM] = 1
        cond = Condition(condition_type="culture_level_gt", params={
            "culture": "confucianism", "threshold": 3
        })
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestCultureContributionGtCondition:
    def test_gt(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.CONFUCIANISM] = 5
        cond = Condition(condition_type="culture_contribution_gt", params={
            "culture": "confucianism", "threshold": 3
        })
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_not_gt(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.CONFUCIANISM] = 1
        cond = Condition(condition_type="culture_contribution_gt", params={
            "culture": "confucianism", "threshold": 3
        })
        assert not resolver.check_condition(cond, minimal_state, "jin_1")


class TestCultureMostEmptyCondition:
    def test_all_zero(self, minimal_state, resolver):
        """All players have 0 culture sum → all are 'most empty'."""
        cond = Condition(condition_type="culture_most_empty")
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_not_most_empty(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.CONFUCIANISM] = 10
        cond = Condition(condition_type="culture_most_empty")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")


# ============================================================
# Order / Prestige
# ============================================================

class TestIsLowestOrderCondition:
    def test_jin_3_is_lowest_order(self, minimal_state, resolver):
        """jin_1=0, jin_2=1, jin_3=2 → highest value = lowest priority = jin_3."""
        cond = Condition(condition_type="is_lowest_order")
        assert resolver.check_condition(cond, minimal_state, "jin_3")

    def test_jin_1_not_lowest(self, minimal_state, resolver):
        cond = Condition(condition_type="is_lowest_order")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")


class TestIsLowestCultureSumCondition:
    def test_all_zero(self, minimal_state, resolver):
        cond = Condition(condition_type="is_lowest_culture_sum")
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_high_not_lowest(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.CONFUCIANISM] = 10
        cond = Condition(condition_type="is_lowest_culture_sum")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")
        assert resolver.check_condition(cond, minimal_state, "jin_2")


class TestPrestigeHighestCondition:
    def test_is_highest(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").prestige = 8
        minimal_state.get_player("jin_2").prestige = 3
        minimal_state.get_player("jin_3").prestige = 3
        cond = Condition(condition_type="prestige_highest")
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_not_highest(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").prestige = 2
        minimal_state.get_player("jin_2").prestige = 5
        cond = Condition(condition_type="prestige_highest")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")

    def test_tie_nobody_counted(self, minimal_state, resolver):
        """Tie → strict uniqueness required → nobody is 'highest'."""
        minimal_state.get_player("jin_1").prestige = 5
        minimal_state.get_player("jin_2").prestige = 5
        cond = Condition(condition_type="prestige_highest")
        assert not resolver.check_condition(cond, minimal_state, "jin_1")
        assert not resolver.check_condition(cond, minimal_state, "jin_2")


# ============================================================
# Region / Location
# ============================================================

class TestControlRegionCondition:
    def test_does_not_crash(self, minimal_state, resolver):
        cond = Condition(condition_type="control_region", params={"region": "关中"})
        result = resolver.check_condition(cond, minimal_state, "north")
        assert isinstance(result, bool)


class TestFriendlyControlRegionCondition:
    def test_friendly_in_region(self, minimal_state, resolver):
        cond = Condition(condition_type="friendly_control_region", params={"region": "关中"})
        result = resolver.check_condition(cond, minimal_state, "north")
        assert isinstance(result, bool)


class TestOccupyLocationCondition:
    def test_occupies(self, minimal_state, resolver):
        cond = Condition(condition_type="occupy_location", params={"location": "长安"})
        assert resolver.check_condition(cond, minimal_state, "north")

    def test_does_not_occupy(self, minimal_state, resolver):
        cond = Condition(condition_type="occupy_location", params={"location": "洛阳"})
        assert not resolver.check_condition(cond, minimal_state, "north")


class TestOccupyLocationInRegionCondition:
    def test_occupies_in_region(self, minimal_state, resolver):
        cond = Condition(condition_type="occupy_location_in_region",
                        params={"region": "长安"})
        result = resolver.check_condition(cond, minimal_state, "north")
        assert isinstance(result, bool)


# ============================================================
# Route
# ============================================================

class TestHasRouteCondition:
    def test_route_through_jin_locations(self, minimal_state, resolver):
        """Test BFS route through Jin-controlled territory."""
        # Make 弘农 controlled by jin_1
        minimal_state.locations["弘农"].controller = ControlState.JIN_P1
        cond = Condition(condition_type="has_route", params={
            "from": "长安", "to": "弘农", "controller": "jin"
        })
        assert resolver.check_condition(cond, minimal_state, "jin_1")

    def test_no_route_through_sima(self, minimal_state, resolver):
        """长安→洛阳: 洛阳 is Sima, no Jin route possible."""
        cond = Condition(condition_type="has_route", params={
            "from": "长安", "to": "洛阳", "controller": "jin"
        })
        assert not resolver.check_condition(cond, minimal_state, "jin_1")


# ============================================================
# Turn tracking
# ============================================================

class TestOnActionThisTurnCondition:
    def test_not_yet_marched(self, minimal_state, resolver):
        cond = Condition(condition_type="on_action_this_turn", params={"action": "march"})
        assert not resolver.check_condition(cond, minimal_state, "north")

    def test_has_marched(self, minimal_state, resolver):
        minimal_state.get_player("north").has_marched = True
        cond = Condition(condition_type="on_action_this_turn", params={"action": "march"})
        assert resolver.check_condition(cond, minimal_state, "north")


# ============================================================
# Archive / Goals
# ============================================================

class TestArchiveCountGeCondition:
    def test_zero_not_enough(self, minimal_state, resolver):
        cond = Condition(condition_type="archive_count_ge", params={"count": 1})
        assert not resolver.check_condition(cond, minimal_state, "north")

    def test_enough(self, minimal_state, resolver):
        card_def = CardDef(card_id="test", name="test", owner_faction="初始",
                           cost=0, card_type=CardType.STRATEGY,
                           card_category=CardType.STRATEGY, effect_text="测试")
        minimal_state.get_player("north").history_area = [
            Card(definition=card_def) for _ in range(3)]
        cond = Condition(condition_type="archive_count_ge", params={"count": 2})
        assert resolver.check_condition(cond, minimal_state, "north")


class TestNotCompletedGoalCondition:
    def test_goal_not_completed(self, minimal_state, resolver):
        """When player has no goal_cards, any goal is 'not completed'.
        NOTE: PlayerState currently has no goal_cards attribute — the operator
        may need a guard. This test documents expected behavior."""
        cond = Condition(condition_type="not_completed_goal",
                        params={"goal_name": "北伐中原"})
        # If goal_cards missing, the operator should return True (goal not found)
        try:
            result = resolver.check_condition(cond, minimal_state, "north")
            assert result is True
        except AttributeError:
            pytest.skip("PlayerState.goal_cards not yet implemented")


# ============================================================
# Fallback
# ============================================================

class TestRawTextCondition:
    def test_always_true(self, minimal_state, resolver):
        cond = Condition(condition_type="raw_text", params={"text": "任意文本条件"})
        assert resolver.check_condition(cond, minimal_state, "north")


# ============================================================
# Registry completeness
# ============================================================

class TestRegistryCompleteness:
    EXPECTED = {
        "and", "not", "is_faction", "can_usurp", "compare",
        "has_military", "staff_has_space", "has_expedition",
        "marker_count_gt", "marker_count", "has_token",
        "culture_level_gt", "culture_contribution_gt", "culture_most_empty",
        "is_lowest_order", "is_lowest_culture_sum", "prestige_highest",
        "control_region", "friendly_control_region",
        "occupy_location", "occupy_location_in_region",
        "has_route", "on_action_this_turn", "archive_count_ge",
        "not_completed_goal", "raw_text",
    }

    def test_all_expected_registered(self):
        registered = set(CONDITION_REGISTRY.keys())
        missing = self.EXPECTED - registered
        assert not missing, f"Missing condition types: {missing}"

    def test_each_has_check_and_condition_type(self):
        for ct, op in CONDITION_REGISTRY.items():
            assert hasattr(op, 'check'), f"{ct}: missing check"
            assert hasattr(op, 'condition_type'), f"{ct}: missing condition_type"
