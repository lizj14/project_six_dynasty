"""测试变量 X 解析系统 — _resolve_value() 所有变量源。

覆盖:
  - 字面量/整数
  - X + variable_source (军事/文化/内政/权谋)
  - X + variable_source + max (上限)
  - sum + sources
  - 标准变量: hand_size, prestige, contribution, history_count, control_count
  - 标记变量: marker_count_military/culture/affair/power
  - 文化贡献: confucianism_contribution, taoism_contribution, buddhism_contribution
  - 特殊计数: jin_court_refugee_count, neutral_count_in_regions
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import (
    FactionType, CardType, MarkerType, CultureType, ControlState,
)
from models.card import CardDef, Card
from models.location import LocationState
from models.game_state import GameState, CultureTrackState
from cards.effect_resolver import EffectResolver


@pytest.fixture
def resolver():
    return EffectResolver()


def _card_def(card_id="test"):
    """Convenience: create a minimal CardDef."""
    return CardDef(
        card_id=card_id, name="测试卡", owner_faction="初始",
        cost=0, card_type=CardType.STRATEGY,
        card_category=CardType.STRATEGY, effect_text="测试",
    )


# ============================================================
# Literal values
# ============================================================

class TestLiteralValues:
    def test_int(self, minimal_state, resolver):
        assert resolver._resolve_value(5, minimal_state, "north") == 5

    def test_zero(self, minimal_state, resolver):
        assert resolver._resolve_value(0, minimal_state, "north") == 0

    def test_negative(self, minimal_state, resolver):
        assert resolver._resolve_value(-3, minimal_state, "north") == -3

    def test_numeric_string(self, minimal_state, resolver):
        assert resolver._resolve_value("7", minimal_state, "north") == 7

    def test_none_is_zero(self, minimal_state, resolver):
        assert resolver._resolve_value(None, minimal_state, "north") == 0


# ============================================================
# X with variable_source
# ============================================================

class TestXWithVariableSource:
    def test_x_from_military_marker(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 4
        params = {"variable_source": "军事", "max": None}
        assert resolver._resolve_value("X", minimal_state, "north", params) == 4

    def test_x_from_culture_marker(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_culture = 3
        params = {"variable_source": "文化"}
        assert resolver._resolve_value("X", minimal_state, "north", params) == 3

    def test_x_from_affair_marker(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_affair = 2
        params = {"variable_source": "内政"}
        assert resolver._resolve_value("X", minimal_state, "north", params) == 2

    def test_x_from_power_marker(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_power = 5
        params = {"variable_source": "权谋"}
        assert resolver._resolve_value("X", minimal_state, "north", params) == 5

    def test_x_with_cap(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 7
        params = {"variable_source": "军事", "max": 3}
        assert resolver._resolve_value("X", minimal_state, "north", params) == 3

    def test_x_no_variable_source(self, minimal_state, resolver):
        assert resolver._resolve_value("X", minimal_state, "north") == 0


# ============================================================
# Sum of sources
# ============================================================

class TestSumOfSources:
    def test_sum_single_source(self, minimal_state, resolver):
        params = {"sources": ["hand_size"]}
        assert resolver._resolve_value("sum", minimal_state, "north", params) == 0

    def test_sum_multiple_markers(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.marker_military = 2
        player.marker_culture = 3
        params = {"sources": ["marker_count_military", "marker_count_culture"]}
        assert resolver._resolve_value("sum", minimal_state, "north", params) == 5


# ============================================================
# Standard variables
# ============================================================

class TestStandardVariables:
    def test_hand_size(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.hand = [Card(definition=_card_def()) for _ in range(4)]
        assert resolver._resolve_value("hand_size", minimal_state, "north") == 4

    def test_prestige(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").prestige = 6
        assert resolver._resolve_value("prestige", minimal_state, "jin_1") == 6

    def test_contribution(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").contribution = 7
        assert resolver._resolve_value("contribution", minimal_state, "jin_1") == 7

    def test_history_count(self, minimal_state, resolver):
        player = minimal_state.get_player("north")
        player.history_area = [Card(definition=_card_def()) for _ in range(2)]
        assert resolver._resolve_value("history_count", minimal_state, "north") == 2

    def test_control_count(self, minimal_state, resolver):
        count = resolver._resolve_value("control_count", minimal_state, "north")
        assert count >= 1  # At minimum controls 长安


# ============================================================
# Marker variables (via get_marker)
# ============================================================

class TestMarkerVariables:
    def test_marker_military(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_military = 3
        assert resolver._resolve_value("marker_count_military", minimal_state, "north") == 3

    def test_marker_culture(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_culture = 4
        assert resolver._resolve_value("marker_count_culture", minimal_state, "north") == 4

    def test_marker_affair(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_affair = 2
        assert resolver._resolve_value("marker_count_affair", minimal_state, "north") == 2

    def test_marker_power(self, minimal_state, resolver):
        minimal_state.get_player("north").marker_power = 1
        assert resolver._resolve_value("marker_count_power", minimal_state, "north") == 1


# ============================================================
# Culture contribution variables
# ============================================================

class TestCultureContributionVariables:
    def test_confucianism(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.CONFUCIANISM] = 5
        assert resolver._resolve_value("confucianism_contribution", minimal_state, "jin_1") == 5

    def test_taoism(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.TAOISM] = 3
        assert resolver._resolve_value("taoism_contribution", minimal_state, "jin_1") == 3

    def test_buddhism(self, minimal_state, resolver):
        minimal_state.get_player("jin_1").culture_contributions[CultureType.BUDDHISM] = 4
        assert resolver._resolve_value("buddhism_contribution", minimal_state, "jin_1") == 4

    def test_zero_when_unset(self, minimal_state, resolver):
        assert resolver._resolve_value("confucianism_contribution", minimal_state, "jin_1") == 0


# ============================================================
# Jin court refugee count
# ============================================================

class TestJinCourtRefugeeCount:
    def test_no_refugees(self, minimal_state, resolver):
        assert resolver._resolve_value("jin_court_refugee_count", minimal_state, "north") == 0

    def test_counts_refugees(self, minimal_state, resolver):
        refugee_def = CardDef(card_id="initial_流民", name="流民", owner_faction="初始",
                              cost=0, card_type=CardType.STRATEGY,
                              card_category=CardType.STRATEGY, effect_text="流民")
        minimal_state.jin_court = [
            Card(definition=refugee_def),
            Card(definition=refugee_def),
        ]
        assert resolver._resolve_value("jin_court_refugee_count", minimal_state, "north") == 2

    def test_only_counts_refugees(self, minimal_state, resolver):
        refugee_def = CardDef(card_id="流民", name="流民", owner_faction="初始",
                              cost=0, card_type=CardType.STRATEGY,
                              card_category=CardType.STRATEGY, effect_text="流民")
        soldier_def = CardDef(card_id="士兵", name="士兵", owner_faction="初始",
                              cost=0, card_type=CardType.STRATEGY,
                              card_category=CardType.STRATEGY, effect_text="士兵")
        minimal_state.jin_court = [
            Card(definition=refugee_def),
            Card(definition=soldier_def),
        ]
        assert resolver._resolve_value("jin_court_refugee_count", minimal_state, "north") == 1


# ============================================================
# Neutral count in regions
# ============================================================

class TestNeutralCountInRegions:
    def test_with_region_param(self, minimal_state, resolver):
        params = {"regions": ["弘农"]}
        count = resolver._resolve_value("neutral_count_in_regions",
                                        minimal_state, "north", params)
        assert isinstance(count, int)

    def test_empty_regions(self, minimal_state, resolver):
        params = {"regions": []}
        count = resolver._resolve_value("neutral_count_in_regions",
                                        minimal_state, "north", params)
        assert count == 0
