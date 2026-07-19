"""Tests for SnapshotViewport — frozen serializable snapshots."""

import json
import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType

from viewport.snapshot import SnapshotViewport


def make_test_state():
    """Minimal test state with 4 players and basic map."""
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

    hero_def = CardDef(
        card_id="hero_test", name="测试英雄", owner_faction="通用",
        cost=-1, card_type=CardType.HERO, card_category=CardCategory.HERO_JIN,
        effect_text="", start_order=5,
    )
    hero_card = Card(definition=hero_def, owner_player_id="north")

    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=25, army_reserve_count=8, army_placed_count=2,
        hand=[hand_card], hero=hero_card, staff_area=[], history_area=[],
        has_expedition_marker=True,
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


class TestSnapshotViewportCreation:
    """Snapshot creation and basic access."""

    def test_from_state_creates_snapshot(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        assert snap.viewer_id == "north"
        assert snap.mode == "snapshot"
        assert snap.round == 3

    def test_from_state_with_actions(self):
        state = make_test_state()
        # No actions available
        snap = SnapshotViewport.from_state(state, "jin_1", [])
        actions = snap.get_available_actions()
        assert isinstance(actions, dict)

    def test_snapshot_is_same_for_same_state(self):
        """Two snapshots from the same state should be identical."""
        state = make_test_state()
        snap1 = SnapshotViewport.from_state(state, "north")
        snap2 = SnapshotViewport.from_state(state, "north")
        assert snap1.to_dict() == snap2.to_dict()

    def test_different_viewers_see_different_private(self):
        state = make_test_state()
        snap_north = SnapshotViewport.from_state(state, "north")
        snap_jin = SnapshotViewport.from_state(state, "jin_1")
        # Public info is the same
        assert snap_north.to_dict()["public"] == snap_jin.to_dict()["public"]
        # Private info is different
        assert snap_north.to_dict()["private"] != snap_jin.to_dict()["private"]


class TestSnapshotViewportJSON:
    """Snapshot JSON serialization."""

    def test_to_json_returns_string(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        json_str = snap.to_json()
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_json_is_valid(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        json_str = snap.to_json()
        data = json.loads(json_str)
        assert data["viewer_id"] == "north"
        assert data["round"] == 3

    def test_json_contains_public_map(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        json_str = snap.to_json()
        data = json.loads(json_str)
        assert "长安" in data["public"]["map"]["locations"]

    def test_json_hand_is_private(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        data = snap.to_dict()
        # Hand is in private section, not in public players
        assert len(data["private"]["hand"]) == 1
        assert "hand" not in data["public"]["players"]["north"]


class TestSnapshotViewportAccessors:
    """All accessor methods return correct data."""

    def test_get_my_hand(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        hand = snap.get_my_hand()
        assert len(hand) == 1
        assert hand[0]["name"] == "测试幕僚"

    def test_get_other_player_hides_hand(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "jin_1")
        north = snap.get_other_player("north")
        assert north["hand_count"] == 1
        assert "hand" not in north

    def test_get_all_locations(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        locs = snap.get_all_locations()
        assert len(locs) == 3
        assert locs["长安"]["controller"] == "north"
        assert locs["弘农"]["controller"] == "empty"

    def test_get_vp_track(self):
        state = make_test_state()
        state.vp_track = {"north": 25, "jin_1": 30}
        snap = SnapshotViewport.from_state(state, "north")
        track = snap.get_vp_track()
        assert track["north"] == 25

    def test_get_deck_counts(self):
        state = make_test_state()
        state.main_deck = [None] * 45
        state.north_deck = [None] * 12
        state.jin_deck = [None] * 18
        snap = SnapshotViewport.from_state(state, "north")
        assert snap.get_main_deck_count() == 45
        assert snap.get_national_deck_count("north") == 12
        assert snap.get_national_deck_count("jin") == 18

    def test_get_nonexistent_player(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        assert snap.get_other_player("nonexistent") == {}

    def test_get_my_player_has_private(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        me = snap.get_my_player()
        assert "hand" in me
        assert len(me["hand"]) == 1
        assert me["military"] == 5
        assert me["vp"] == 25


class TestSnapshotViewportImmutability:
    """Snapshot is deeply immutable."""

    def test_modifying_returned_dict_doesnt_affect_snapshot(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        locs = snap.get_all_locations()
        # Modifying the returned copy should not affect stored snapshot
        locs["fake"] = {"controller": "x"}
        locs2 = snap.get_all_locations()
        assert "fake" not in locs2

    def test_modifying_hand_doesnt_affect_snapshot(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        hand = snap.get_my_hand()
        hand.clear()
        hand2 = snap.get_my_hand()
        assert len(hand2) == 1  # unchanged

    def test_to_dict_is_consistent(self):
        state = make_test_state()
        snap = SnapshotViewport.from_state(state, "north")
        d1 = snap.to_dict()
        d2 = snap.to_dict()
        assert d1 == d2
