"""Tests for LiveViewport — live proxy visibility filtering."""

import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType

from viewport.live import LiveViewport
from viewport.utils import card_to_summary


def make_test_state():
    """Minimal test state with 4 players and basic map."""
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=ControlState.EMPTY),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
        "建康": LocationState(location_id="建康", controller=ControlState.JIN_P1),
    }
    adjs = [
        AdjacencyDef("长安", "弘农", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
        AdjacencyDef("洛阳", "建康", TerrainType.SIMPLE),
    ]

    # Create a hand card for north
    card_def = CardDef(
        card_id="test_friend_1", name="测试幕僚", owner_faction="通用",
        cost=1, card_type=CardType.FRIEND, card_category=CardCategory.FRIEND_MILITARY,
        effect_text="登场: +2军力", marker_military=1, is_friend=True,
    )
    hand_card = Card(definition=card_def, owner_player_id="north")

    # Hero card
    hero_def = CardDef(
        card_id="hero_test", name="测试英雄", owner_faction="通用",
        cost=-1, card_type=CardType.HERO, card_category=CardCategory.HERO_JIN,
        effect_text="", start_order=5,
    )
    hero_card = Card(definition=hero_def, owner_player_id="north")

    # Staff card for north
    staff_def = CardDef(
        card_id="staff_test", name="测试幕僚2", owner_faction="通用",
        cost=2, card_type=CardType.FRIEND, card_category=CardCategory.FRIEND_MILITARY,
        effect_text="被动: 摸牌时+1VP", marker_culture=2, is_friend=True,
    )
    staff_card = Card(definition=staff_def, owner_player_id="north")

    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=25, army_reserve_count=8, army_placed_count=2,
        hand=[hand_card],
        hero=hero_card,
        staff_area=[staff_card],
        history_area=[],
        has_expedition_marker=True,
    )

    # Jin player with hand cards (hidden from others)
    jin_hand_card = Card(definition=CardDef(
        card_id="jin_secret", name="秘密策略", owner_faction="东晋",
        cost=1, card_type=CardType.STRATEGY, card_category=CardCategory.STRATEGY_MILITARY,
        effect_text="牌组行动: 进军",
    ), owner_player_id="jin_1")

    jin_players = [
        PlayerState(player_id="jin_1", faction=FactionType.JIN,
                    military=3, vp=30, prestige=4, contribution=6, order=2,
                    army_reserve_count=10, army_placed_count=1,
                    hand=[jin_hand_card]),
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


class TestLiveViewportBasic:
    """Basic LiveViewport properties."""

    def test_viewer_id(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        assert vp.viewer_id == "north"
        assert vp.mode == "live"

    def test_round_and_phase(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        assert vp.round == 3
        assert vp.phase == "action"

    def test_turn_order(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        assert vp.turn_order == ["north", "jin_1", "jin_2", "jin_3"]

    def test_active_player_index(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        assert vp.active_player_index == 0


class TestLiveViewportPublicInfo:
    """Public info is the same for all viewers."""

    def test_locations_public(self):
        state = make_test_state()
        vp_north = LiveViewport(state, "north")
        vp_jin = LiveViewport(state, "jin_1")
        locs_n = vp_north.get_all_locations()
        locs_j = vp_jin.get_all_locations()
        assert locs_n == locs_j
        assert "长安" in locs_n
        assert locs_n["长安"]["controller"] == "north"
        assert locs_n["弘农"]["controller"] == "empty"

    def test_vp_track_public(self):
        state = make_test_state()
        state.vp_track = {"north": 25, "jin_1": 30, "jin_2": 22, "jin_3": 28, "sima": 15}
        vp = LiveViewport(state, "jin_2")
        track = vp.get_vp_track()
        assert track["north"] == 25
        assert track["jin_1"] == 30

    def test_prestige_track_public(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        track = vp.get_prestige_track()
        assert track["jin_1"] == 4
        assert track["jin_2"] == 5

    def test_deck_counts_only(self):
        state = make_test_state()
        state.main_deck = [None] * 45  # 45 cards in deck
        state.main_discard = []
        vp = LiveViewport(state, "north")
        assert vp.get_main_deck_count() == 45
        # Discard is public (face-up)
        assert vp.get_main_discard() == []


class TestLiveViewportPrivateInfo:
    """Private info is only visible to the owning player."""

    def test_my_hand_is_visible(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        hand = vp.get_my_hand()
        assert len(hand) == 1
        assert hand[0]["name"] == "测试幕僚"
        assert hand[0]["card_type"] == "friend"

    def test_other_player_hand_is_hidden(self):
        """Public player summary only shows hand COUNT, not contents."""
        state = make_test_state()
        vp = LiveViewport(state, "north")
        jin1 = vp.get_other_player("jin_1")
        # Public summary shows hand_count but not hand contents
        assert jin1["hand_count"] == 1
        assert "hand" not in jin1  # hand field is private only

    def test_my_player_includes_private(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        me = vp.get_my_player()
        assert "hand" in me
        assert me["hand"]["count"] == 1
        assert me["hand"]["names"] == ["测试幕僚"]
        assert me["hero"]["name"] == "测试英雄"

    def test_staff_area_public(self):
        """Staff area is face-up and visible to all."""
        state = make_test_state()
        vp = LiveViewport(state, "jin_1")
        north = vp.get_other_player("north")
        assert north["staff_count"] == 1
        assert "测试幕僚2" in north["staff_names"]

    def test_other_hand_only_count(self):
        state = make_test_state()
        vp = LiveViewport(state, "jin_2")
        north = vp.get_other_player("north")
        assert north["hand_count"] == 1
        # Should NOT contain hand cards
        assert "hand" not in north


class TestLiveViewportReturnsCopies:
    """LiveViewport always returns fresh copies, never internal references."""

    def test_locations_are_copies(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        locs1 = vp.get_all_locations()
        locs2 = vp.get_all_locations()
        # Different dict objects
        assert locs1 is not locs2
        # Mutating returned dict doesn't affect GameState
        locs1["fake"] = {"controller": "x"}
        assert "fake" not in state.locations

    def test_hand_is_copy(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        hand1 = vp.get_my_hand()
        hand2 = vp.get_my_hand()
        assert hand1 is not hand2
        hand1.clear()
        assert len(state.north_player.hand) == 1  # unchanged

    def test_public_players_are_copies(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        players1 = vp.get_all_players_public()
        players2 = vp.get_all_players_public()
        assert players1 is not players2

    def test_vp_track_is_copy(self):
        state = make_test_state()
        state.vp_track = {"north": 1}
        vp = LiveViewport(state, "north")
        track = vp.get_vp_track()
        track["north"] = 999
        assert state.vp_track["north"] == 1  # unchanged


class TestLiveViewportJinSpecific:
    """Jin-specific public fields."""

    def test_jin_player_has_prestige(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        jin1 = vp.get_other_player("jin_1")
        assert jin1["prestige"] == 4
        assert jin1["contribution"] == 6
        assert jin1["order"] == 2

    def test_north_player_no_jin_fields(self):
        state = make_test_state()
        vp = LiveViewport(state, "jin_1")
        north = vp.get_other_player("north")
        assert "prestige" not in north
        assert "contribution" not in north


class TestLiveViewportMapQueries:
    """Map query methods."""

    def test_friendly_locations(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        friendly = vp.get_friendly_locations()
        assert "长安" in friendly  # north-controlled

    def test_adjacent_locations(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        adj = vp.get_adjacent_locations("长安")
        assert "弘农" in adj

    def test_get_location(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        loc = vp.get_location("洛阳")
        assert loc is not None
        assert loc["controller"] == "sima"
        assert loc["is_fortified"] is False

    def test_get_nonexistent_location(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        assert vp.get_location("不存在的") is None


class TestLiveViewportToDict:
    """Full serialization."""

    def test_to_dict_has_required_keys(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        data = vp.to_dict()
        assert data["viewer_id"] == "north"
        assert data["round"] == 3
        assert "public" in data
        assert "private" in data
        assert "available_actions" in data

    def test_private_section_has_hand(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        data = vp.to_dict()
        assert len(data["private"]["hand"]) == 1
        assert data["private"]["hand"][0]["name"] == "测试幕僚"

    def test_public_players_dont_have_hand(self):
        state = make_test_state()
        vp = LiveViewport(state, "north")
        data = vp.to_dict()
        north_public = data["public"]["players"]["north"]
        assert north_public["hand_count"] == 1
        assert "hand" not in north_public
