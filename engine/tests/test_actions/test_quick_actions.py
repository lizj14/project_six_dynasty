"""Tests for Occupy, Draw, Recruit, and Fortify quick actions."""

import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType


def make_test_state():
    """Minimal test state with one north player and basic map."""
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=ControlState.EMPTY),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
    }
    adjs = [
        AdjacencyDef("长安", "弘农", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
    ]
    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=0, army_reserve_count=8, army_placed_count=1,
    )
    jin_players = [
        PlayerState(player_id="jin_1", faction=FactionType.JIN, military=1, army_reserve_count=8),
        PlayerState(player_id="jin_2", faction=FactionType.JIN, military=1, army_reserve_count=8),
        PlayerState(player_id="jin_3", faction=FactionType.JIN, military=1, army_reserve_count=8),
    ]
    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=north, jin_players=jin_players,
        locations=locs, map_adjacencies=adjs,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0, seed=42,
    )
    return state


class TestOccupyAction:
    """Tests for occupy (占据)."""

    def test_occupy_valid(self):
        from engine.actions.quick_actions import OccupyAction
        state = make_test_state()
        action = OccupyAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert result.success, f"Expected valid occupy, got: {result.error}"

    def test_occupy_insufficient_military(self):
        from engine.actions.quick_actions import OccupyAction
        state = make_test_state()
        state.north_player.military = 0
        action = OccupyAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert not result.success

    def test_occupy_already_occupied(self):
        from engine.actions.quick_actions import OccupyAction
        state = make_test_state()
        action = OccupyAction(player_id="north", target_location="洛阳")  # Sima controlled
        result = action.validate(state)
        assert not result.success

    def test_occupy_not_adjacent(self):
        from engine.actions.quick_actions import OccupyAction
        state = make_test_state()
        action = OccupyAction(player_id="north", target_location="洛阳")  # Not adjacent to 长安
        result = action.validate(state)
        assert not result.success

    def test_occupy_execute(self):
        from engine.actions.quick_actions import OccupyAction
        state = make_test_state()
        action = OccupyAction(player_id="north", target_location="弘农")
        result = action.execute(state)
        assert result.success
        assert state.locations["弘农"].controller == ControlState.NORTH
        assert state.north_player.military == 4  # 5 - 1
        assert state.north_player.army_placed_count == 2


class TestDrawAction:
    """Tests for draw (摸牌) quick action."""

    def test_draw_valid(self):
        from engine.actions.quick_actions import DrawAction
        state = make_test_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY, effect_text="",
        )
        state.main_deck = [Card(definition=card_def)]
        action = DrawAction(player_id="north")
        result = action.validate(state)
        assert result.success

    def test_draw_once_per_turn(self):
        from engine.actions.quick_actions import DrawAction
        state = make_test_state()
        state.north_player.has_drawn_quick = True
        action = DrawAction(player_id="north")
        result = action.validate(state)
        assert not result.success

    def test_draw_empty_deck(self):
        from engine.actions.quick_actions import DrawAction
        state = make_test_state()
        action = DrawAction(player_id="north")
        result = action.validate(state)
        assert not result.success  # No cards in main deck

    def test_draw_execute(self):
        from engine.actions.quick_actions import DrawAction
        state = make_test_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY, effect_text="",
        )
        state.main_deck = [Card(definition=card_def)]
        action = DrawAction(player_id="north")
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.hand) == 1
        assert state.north_player.military == 3  # 5 - 2
        assert state.north_player.has_drawn_quick


class TestRecruitAction:
    """Tests for recruit (征募) quick action."""

    def test_recruit_valid(self):
        from engine.actions.quick_actions import RecruitAction
        state = make_test_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=1, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY, effect_text="",
        )
        state.north_player.hand = [Card(definition=card_def)]
        action = RecruitAction(player_id="north", card_to_discard_index=0)
        result = action.validate(state)
        assert result.success

    def test_recruit_no_cards(self):
        from engine.actions.quick_actions import RecruitAction
        state = make_test_state()
        action = RecruitAction(player_id="north", card_to_discard_index=0)
        result = action.validate(state)
        assert not result.success

    def test_recruit_execute(self):
        from engine.actions.quick_actions import RecruitAction
        state = make_test_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=1, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY, effect_text="",
        )
        state.north_player.hand = [Card(definition=card_def)]
        action = RecruitAction(player_id="north", card_to_discard_index=0)
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.hand) == 0
        assert state.north_player.military == 6  # 5 + 1
        assert len(state.main_discard) == 1


class TestFortifyAction:
    """Tests for fortify (加固) quick action."""

    def test_fortify_valid(self):
        from engine.actions.quick_actions import FortifyAction
        state = make_test_state()
        action = FortifyAction(player_id="north", target_location="长安")
        result = action.validate(state)
        assert result.success

    def test_fortify_not_friendly(self):
        from engine.actions.quick_actions import FortifyAction
        state = make_test_state()
        action = FortifyAction(player_id="north", target_location="弘农")  # Neutral
        result = action.validate(state)
        assert not result.success

    def test_fortify_already_fortified(self):
        from engine.actions.quick_actions import FortifyAction
        state = make_test_state()
        state.locations["长安"].is_fortified = True
        action = FortifyAction(player_id="north", target_location="长安")
        result = action.validate(state)
        assert not result.success

    def test_fortify_once_per_turn(self):
        from engine.actions.quick_actions import FortifyAction
        state = make_test_state()
        state.north_player.has_fortified_quick = True
        action = FortifyAction(player_id="north", target_location="长安")
        result = action.validate(state)
        assert not result.success

    def test_fortify_execute(self):
        from engine.actions.quick_actions import FortifyAction
        state = make_test_state()
        action = FortifyAction(player_id="north", target_location="长安")
        result = action.execute(state)
        assert result.success
        assert state.locations["长安"].is_fortified
        assert state.north_player.military == 4  # 5 - 1
        assert state.north_player.has_fortified_quick
