"""Tests for Convert, Archive, SpreadCulture, Search, Draft, and Order actions."""

import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType


def make_state():
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=ControlState.SIMA),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.NEUTRAL),
    }
    adjs = [
        AdjacencyDef("长安", "弘农", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
    ]
    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=0, army_reserve_count=8, army_placed_count=1,
    )
    jin1 = PlayerState(
        player_id="jin_1", faction=FactionType.JIN,
        military=5, vp=0, prestige=0, contribution=0,
        army_reserve_count=8, army_placed_count=1,
    )
    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=north,
        jin_players=[jin1,
            PlayerState(player_id="jin_2", faction=FactionType.JIN, army_reserve_count=8),
            PlayerState(player_id="jin_3", faction=FactionType.JIN, army_reserve_count=8),
        ],
        locations=locs, map_adjacencies=adjs,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0, seed=42,
    )
    return state


class TestConvertAction:
    """Tests for convert (转化)."""

    def test_convert_enemy_location(self):
        from engine.actions.special_actions import ConvertAction
        state = make_state()
        action = ConvertAction(player_id="north", target_location="弘农")
        result = action.execute(state)
        assert result.success
        assert state.locations["弘农"].controller == ControlState.NORTH
        assert state.north_player.vp == 1

    def test_convert_neutral_location(self):
        from engine.actions.special_actions import ConvertAction
        state = make_state()
        action = ConvertAction(player_id="north", target_location="洛阳")
        result = action.execute(state)
        assert result.success
        assert state.locations["洛阳"].controller == ControlState.NORTH
        assert state.north_player.vp == 1

    def test_convert_jin_gains_prestige(self):
        from engine.actions.special_actions import ConvertAction
        state = make_state()
        # Jin player must convert a NON-friendly location to get prestige
        # 弘农 is Sima-controlled, which IS friendly to Jin
        # Change: target the North location for prestige gain
        state.locations["长安"].controller = ControlState.NORTH
        state.locations["弘农"].controller = ControlState.NORTH  # Now North-controlled
        state.jin_players[0].army_placed_count = 1  # Jin has army at 洛阳
        state.locations["洛阳"].controller = ControlState.JIN_P1
        action = ConvertAction(player_id="jin_1", target_location="弘农")
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].prestige == 1
        assert state.jin_players[0].vp == 1

    def test_convert_own_location_blocked(self):
        from engine.actions.special_actions import ConvertAction
        state = make_state()
        action = ConvertAction(player_id="north", target_location="长安")
        result = action.validate(state)
        assert not result.success

    def test_convert_removes_fortification(self):
        from engine.actions.special_actions import ConvertAction
        state = make_state()
        state.locations["弘农"].is_fortified = True
        action = ConvertAction(player_id="north", target_location="弘农")
        action.execute(state)
        assert not state.locations["弘农"].is_fortified


class TestArchiveAction:
    """Tests for archive (存档)."""

    def test_archive_from_hand(self):
        from engine.actions.special_actions import ArchiveAction
        state = make_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=1, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="", history_vp=5,
        )
        state.north_player.hand = [Card(definition=card_def)]
        action = ArchiveAction(player_id="north", card_index=0, source="hand")
        result = action.execute(state)
        assert result.success
        assert len(state.north_player.hand) == 0
        assert len(state.north_player.history_area) == 1
        assert state.north_player.vp == 5  # history_vp

    def test_archive_jin_gains_contribution(self):
        from engine.actions.special_actions import ArchiveAction
        state = make_state()
        card_def = CardDef(
            card_id="test_1", name="test_card", owner_faction="通用",
            cost=1, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="", history_vp=3,
        )
        state.jin_players[0].hand = [Card(definition=card_def)]
        action = ArchiveAction(player_id="jin_1", card_index=0, source="hand")
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].contribution == 1
        assert state.jin_players[0].vp == 3


class TestSpreadCulture:
    """Tests for spread_culture (传播文化)."""

    def test_spread_culture_basic(self):
        from engine.actions.special_actions import SpreadCultureAction
        from models.enums import CultureType, Region, ControlState
        from models.location import RegionState
        from models.game_state import CultureTrackState
        state = make_state()
        # Set up region control for 关中 so validation passes
        state.regions[Region.GUANZHONG] = RegionState(region=Region.GUANZHONG)
        state.regions[Region.GUANZHONG].control_marker = ControlState.NORTH
        state.culture_tracks[CultureType.CONFUCIANISM] = CultureTrackState(
            culture=CultureType.CONFUCIANISM)
        action = SpreadCultureAction(
            player_id="north", culture_type="confucianism",
            target_region="关中"
        )
        result = action.execute(state)
        assert result.success
        # VP based on marker count (0 existing + 1 new = 1, cap 5)
        assert state.north_player.vp >= 1


class TestSearchAction:
    """Tests for search (检索)."""

    def test_search_finds_card(self):
        from engine.actions.special_actions import SearchAction
        from models.enums import CardType, CardCategory
        state = make_state()
        # Put a strategy card in deck
        strategy = CardDef(
            card_id="s1", name="test_strategy", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_MILITARY,
            effect_text="",
        )
        non_strategy = CardDef(
            card_id="e1", name="test_event", owner_faction="通用",
            cost=0, card_type=CardType.EVENT,
            card_category=CardCategory.EVENT_UTILITY,
            effect_text="",
        )
        state.main_deck = [
            Card(definition=non_strategy),
            Card(definition=strategy),
        ]
        action = SearchAction(player_id="north", search_count=1, search_type="strategy")
        result = action.execute(state)
        assert result.success
        # Should have found the strategy card
        found = any("test_strategy" in str(e) for e in result.events)
        assert found
        assert len(state.north_player.hand) == 1


class TestDraftAction:
    """Tests for levy (征发)."""

    def test_levy_from_court(self):
        from engine.actions.special_actions import LevyAction
        state = make_state()
        card_def = CardDef(
            card_id="court_1", name="court_card", owner_faction="通用",
            cost=1, card_type=CardType.STRATEGY,
            card_category=CardCategory.STRATEGY_MILITARY,
            effect_text="", resource_option_army=2, resource_option_vp=1,
        )
        state.north_court = [Card(definition=card_def)]
        action = LevyAction(player_id="north", card_id="court_1")
        result = action.execute(state)
        assert result.success
        assert state.north_player.military == 7  # 5 + 2
        assert state.north_player.vp == 1
        assert len(state.north_court) == 0
        assert len(state.north_played_this_round) == 1


class TestOrderActions:
    """Tests for raise/lower order.

    Order is sorted descending (higher = earlier in turn).
    RaiseOrder: order+1 (go earlier). LowerOrder: order-1 (go later).
    """

    def test_raise_order(self):
        from engine.actions.special_actions import RaiseOrderAction
        state = make_state()
        state.jin_players[0].order = 3
        action = RaiseOrderAction(player_id="jin_1", amount=1)
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].order == 4  # Higher = earlier

    def test_raise_order_not_jin(self):
        from engine.actions.special_actions import RaiseOrderAction
        state = make_state()
        action = RaiseOrderAction(player_id="north")
        result = action.validate(state)
        assert not result.success

    def test_lower_order(self):
        from engine.actions.special_actions import LowerOrderAction
        state = make_state()
        state.jin_players[0].order = 2
        action = LowerOrderAction(player_id="jin_1", target_player_id="jin_1", amount=1)
        result = action.execute(state)
        assert result.success
        assert state.jin_players[0].order == 1  # Lower = later
