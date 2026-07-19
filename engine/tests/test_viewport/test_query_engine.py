"""Tests for QueryEngine — path-based CLI queries."""

import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType

from viewport.live import LiveViewport
from viewport.snapshot import SnapshotViewport
from viewport.query import QueryEngine


def make_test_state():
    """Minimal test state with 4 players."""
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=ControlState.EMPTY),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
    }
    adjs = [
        AdjacencyDef("长安", "弘农", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
    ]

    card_def = CardDef(
        card_id="test_friend_1", name="测试幕僚", owner_faction="通用",
        cost=1, card_type=CardType.FRIEND, card_category=CardCategory.FRIEND_MILITARY,
        effect_text="登场: +2军力", marker_military=1, is_friend=True,
    )
    hand_card = Card(definition=card_def, owner_player_id="north")

    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=25, army_reserve_count=8, army_placed_count=2,
        hand=[hand_card], hero=None, staff_area=[], history_area=[],
    )

    jin_players = [
        PlayerState(player_id="jin_1", faction=FactionType.JIN,
                    military=3, vp=30, prestige=4, contribution=6, order=2,
                    army_reserve_count=10, army_placed_count=1),
        PlayerState(player_id="jin_2", faction=FactionType.JIN,
                    military=2, vp=22, prestige=5, contribution=4, order=1,
                    army_reserve_count=10, army_placed_count=0),
        PlayerState(player_id="jin_3", faction=FactionType.JIN,
                    military=4, vp=28, prestige=3, contribution=5, order=3,
                    army_reserve_count=10, army_placed_count=0),
    ]

    state = GameState(
        round=3, phase=PhaseType.ACTION,
        north_player=north, jin_players=jin_players,
        locations=locs, map_adjacencies=adjs,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0, seed=42,
        main_deck=[], main_discard=[],
    )
    return state


class TestQueryEngineMy:
    """my.* queries."""

    def test_query_my_hand(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        # Default: names-only
        result = qe.query("my.hand")
        assert isinstance(result, dict)
        assert result["count"] == 1
        assert result["names"] == ["测试幕僚"]
        # .detail: full card summaries
        detail = qe.query("my.hand.detail")
        assert isinstance(detail, list)
        assert len(detail) == 1
        assert detail[0]["name"] == "测试幕僚"
        # .0: single card detail
        single = qe.query("my.hand.0")
        assert single["name"] == "测试幕僚"
        # Out of range
        err = qe.query("my.hand.5")
        assert "error" in err

    def test_query_my_vp(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("my.vp")
        assert result == 25

    def test_query_my_military(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("my.military")
        assert result == 5

    def test_query_my_full(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("my")
        assert isinstance(result, dict)
        assert result["vp"] == 25

    def test_query_my_hero_none(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("my.hero")
        assert result is None

    def test_query_my_case_insensitive(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result_lower = qe.query("my.vp")
        result_upper = qe.query("MY.VP")
        assert result_lower == result_upper


class TestQueryEnginePlayer:
    """player.* queries."""

    def test_query_player_all(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.all")
        assert isinstance(result, list)
        assert len(result) == 4

    def test_query_player_specific(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.jin_1")
        assert result["vp"] == 30
        assert result["hand_count"] == 0

    def test_query_player_field(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.jin_1.vp")
        assert result == 30

    def test_query_player_self_has_private(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.north")
        assert "hand" in result  # self sees private info

    def test_query_player_other_no_private(self):
        state = make_test_state()
        vp = LiveViewport(state, "jin_1")
        qe = QueryEngine(vp)
        result = qe.query("player.north")
        assert "hand" not in result  # can't see north's hand

    def test_query_nonexistent_player(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.ghost")
        assert "error" in result

    def test_query_player_nonexistent_field(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("player.jin_1.nonexistent")
        assert "error" in result


class TestQueryEngineMap:
    """map.* queries."""

    def test_query_map_all(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map.all")
        assert isinstance(result, dict)
        assert "长安" in result

    def test_query_map_specific(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map.长安")
        assert result["controller"] == "north"
        assert result["is_fortified"] is False

    def test_query_map_friendly(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map.friendly")
        assert "长安" in result

    def test_query_map_adjacent(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map.adjacent.长安")
        assert "弘农" in result

    def test_query_map_nonexistent(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map.不存在的")
        assert "error" in result

    def test_query_map_default_is_all(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("map")
        assert isinstance(result, dict)
        assert "长安" in result


class TestQueryEngineTracks:
    """tracks.* queries."""

    def test_query_tracks_vp(self):
        state = make_test_state()
        state.vp_track = {"north": 25, "jin_1": 30}
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("tracks.vp")
        assert result["north"] == 25

    def test_query_tracks_prestige(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("tracks.prestige")
        assert result["jin_1"] == 4
        assert result["jin_2"] == 5

    def test_query_tracks_all(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("tracks")
        assert "vp" in result
        assert "prestige" in result


class TestQueryEngineDecks:
    """deck.* queries."""

    def test_query_deck_main_count(self):
        state = make_test_state()
        state.main_deck = [None] * 45
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        assert qe.query("deck.main.count") == 45

    def test_query_deck_north(self):
        state = make_test_state()
        state.north_deck = [None] * 12
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        assert qe.query("deck.north.count") == 12

    def test_query_deck_all(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("deck")
        assert "main" in result
        assert "north" in result
        assert "jin" in result

    def test_query_deck_discard(self):
        state = make_test_state()
        card_def = CardDef(card_id="d1", name="弃牌测试", owner_faction="通用",
                          cost=0, card_type=CardType.EVENT, card_category=CardCategory.EVENT_MILITARY,
                          effect_text="")
        state.main_discard = [Card(definition=card_def)]
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("deck.main.discard")
        assert "弃牌测试" in result


class TestQueryEngineSpecial:
    """Special queries."""

    def test_query_summary(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("summary")
        assert isinstance(result, str)
        assert "北方" in result
        assert "north" in result

    def test_query_full(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("full")
        assert isinstance(result, dict)
        assert result["viewer_id"] == "north"

    def test_query_round(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        assert qe.query("round") == 3

    def test_query_phase(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        assert qe.query("phase") == "action"

    def test_query_turn_order(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("turn_order")
        assert result == ["north", "jin_1", "jin_2", "jin_3"]

    def test_query_unknown_namespace(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("unknown.thing")
        assert "error" in result

    def test_query_emperor(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("emperor")
        assert isinstance(result, dict)

    def test_query_sima(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)
        result = qe.query("sima")
        assert isinstance(result, dict)


class TestQueryEngineSnapshot:
    """QueryEngine works with SnapshotViewport too."""

    def test_query_snapshot_my_hand(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        qe = QueryEngine(snap)
        # Default: names-only
        result = qe.query("my.hand")
        assert result["count"] == 1
        assert result["names"] == ["测试幕僚"]
        # .detail: full list
        detail = qe.query("my.hand.detail")
        assert detail[0]["name"] == "测试幕僚"

    def test_query_snapshot_player(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        qe = QueryEngine(snap)
        result = qe.query("player.jin_1.vp")
        assert result == 30

    def test_query_snapshot_map(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        qe = QueryEngine(snap)
        result = qe.query("map.洛阳")
        assert result["controller"] == "sima"

    def test_query_snapshot_summary(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        qe = QueryEngine(snap)
        result = qe.query("summary")
        assert "北方" in result
