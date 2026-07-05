"""Tests for goal card evaluation."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import ControlState, Region, FactionType, PhaseType, CultureType
from models.location import LocationState
from models.player import PlayerState
from models.game_state import GameState
from rules.goals import evaluate_goal, GOAL_DEFINITIONS


def make_state():
    """Minimal state for goal tests."""
    jin1 = PlayerState(player_id="jin_1", faction=FactionType.JIN,
                        vp=10, prestige=5, contribution=5, marker_power=3)
    state = GameState(
        round=10, phase=PhaseType.GAME_OVER,
        north_player=PlayerState(player_id="north", faction=FactionType.NORTH),
        jin_players=[jin1,
            PlayerState(player_id="jin_2", faction=FactionType.JIN, prestige=3),
            PlayerState(player_id="jin_3", faction=FactionType.JIN, prestige=2),
        ],
    )
    return state


class TestGoalConditions:
    """Test individual goal conditions."""

    def test_contribution_goal_simple(self):
        """功绩大于等于7 → simple VP."""
        state = make_state()
        state.jin_players[0].contribution = 7
        goal = GOAL_DEFINITIONS[6]  # 配享太庙: 10/18
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 10  # simple condition met

    def test_contribution_goal_full(self):
        """功绩等于9 → full VP."""
        state = make_state()
        state.jin_players[0].contribution = 9
        goal = GOAL_DEFINITIONS[6]
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 18  # full condition met

    def test_contribution_goal_not_met(self):
        """功绩=5 → neither condition met."""
        state = make_state()
        state.jin_players[0].contribution = 5
        goal = GOAL_DEFINITIONS[6]
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 0

    def test_prestige_goal(self):
        """威望超过6 but not highest-by-3 → only simple VP."""
        state = make_state()
        state.jin_players[0].prestige = 7
        state.jin_players[1].prestige = 6  # Close second: gap=1 < 3
        state.jin_players[2].prestige = 5
        goal = GOAL_DEFINITIONS[7]  # 加九锡: 8/30
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 8  # simple met, full not met (gap too small)

    def test_prestige_highest_with_gap(self):
        """威望最高，超过第二名≥3 → full VP."""
        state = make_state()
        state.jin_players[0].prestige = 8  # highest
        state.jin_players[1].prestige = 3  # second: gap=5≥3
        state.jin_players[2].prestige = 2
        goal = GOAL_DEFINITIONS[7]
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 30

    def test_prestige_highest_insufficient_gap(self):
        """威望最高 but gap < 3 → only simple."""
        state = make_state()
        state.jin_players[0].prestige = 8
        state.jin_players[1].prestige = 6  # gap=2 < 3
        goal = GOAL_DEFINITIONS[7]
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 8  # simple met, full not

    def test_hand_size_goal(self):
        """手牌超过8张 → full VP."""
        state = make_state()
        from models.card import CardDef, Card
        from models.enums import CardType, CardCategory
        dummy = CardDef(card_id="d", name="d", owner_faction="通用",
                         cost=0, card_type=CardType.EVENT,
                         card_category=CardCategory.EVENT_UTILITY, effect_text="")
        state.jin_players[0].hand = [Card(definition=dummy)] * 9
        goal = GOAL_DEFINITIONS[8]  # 家财万贯: 6/12
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 12

    def test_marker_goal(self):
        """拥有3个权谋标记 → simple VP."""
        state = make_state()
        state.jin_players[0].marker_power = 3
        goal = GOAL_DEFINITIONS[9]  # 遗臭万年: 7/14
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 7

    def test_history_goal(self):
        """史书区有8张牌 → full VP."""
        state = make_state()
        from models.card import CardDef, Card
        from models.enums import CardType, CardCategory
        dummy = CardDef(card_id="d", name="d", owner_faction="通用",
                         cost=0, card_type=CardType.EVENT,
                         card_category=CardCategory.EVENT_UTILITY, effect_text="")
        state.jin_players[0].history_area = [Card(definition=dummy)] * 8
        goal = GOAL_DEFINITIONS[14]  # 世说新语: 8/16
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 16

    def test_culture_goal(self):
        """儒学贡献超过5且最高 → full VP."""
        state = make_state()
        state.jin_players[0].culture_contributions[CultureType.CONFUCIANISM] = 6
        state.jin_players[1].culture_contributions[CultureType.CONFUCIANISM] = 2
        state.jin_players[2].culture_contributions[CultureType.CONFUCIANISM] = 1
        goal = GOAL_DEFINITIONS[10]  # 敦悦五经: 6/16
        vp = evaluate_goal(state, "jin_1", goal)
        assert vp == 16
