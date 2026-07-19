"""Integration tests — Viewport with GameState and adapter."""

import json
import pytest
from models.enums import ControlState, TerrainType, FactionType, CardType, CardCategory
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.card import CardDef, Card
from models.game_state import GameState, PhaseType

from viewport import create_viewport, LiveViewport, SnapshotViewport, QueryEngine
from viewport.utils import (
    card_to_summary, card_effect_summary, carddef_to_summary,
    public_player_summary, private_player_summary, full_player_summary,
    location_summary, deep_freeze,
)
from engine.viewport_adapter import (
    create_viewport_for_player, build_snapshot_for_all_players,
    build_public_snapshot,
)


def make_full_state():
    """Full test state with all card zones populated."""
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH, is_fortified=True),
        "弘农": LocationState(location_id="弘农", controller=ControlState.EMPTY),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
        "建康": LocationState(location_id="建康", controller=ControlState.JIN_P1),
    }
    adjs = [
        AdjacencyDef("长安", "弘农", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
        AdjacencyDef("洛阳", "建康", TerrainType.SIMPLE),
    ]

    # North hand
    north_hand = [Card(definition=CardDef(
        card_id="nh1", name="北军策略", owner_faction="北方",
        cost=1, card_type=CardType.STRATEGY, card_category=CardCategory.STRATEGY_MILITARY,
        effect_text="牌组行动: 进军", marker_military=2,
    ), owner_player_id="north")]

    # North staff
    north_staff = [Card(definition=CardDef(
        card_id="ns1", name="王猛", owner_faction="北方",
        cost=2, card_type=CardType.FRIEND, card_category=CardCategory.FRIEND_MILITARY,
        effect_text="被动: 回合开始+1军力", marker_culture=1, is_friend=True,
    ), owner_player_id="north")]

    # North hero
    north_hero = Card(definition=CardDef(
        card_id="hero_n", name="苻坚", owner_faction="北方",
        cost=-1, card_type=CardType.HERO, card_category=CardCategory.HERO_JIN,
        effect_text="", start_order=6, initial_order=1,
    ), owner_player_id="north")

    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=5, vp=30, army_reserve_count=10, army_placed_count=5,
        hand=north_hand, hero=north_hero, staff_area=north_staff,
        history_area=[],
        marker_military=2, marker_culture=1,
        has_expedition_marker=True,
    )

    # Jin players
    jin1_hand = [Card(definition=CardDef(
        card_id="j1h1", name="东晋密策", owner_faction="东晋",
        cost=0, card_type=CardType.EVENT, card_category=CardCategory.EVENT_MILITARY,
        effect_text="摸2张牌",
    ), owner_player_id="jin_1")]

    jin1_staff = [Card(definition=CardDef(
        card_id="j1s1", name="谢安", owner_faction="东晋",
        cost=3, card_type=CardType.FRIEND, card_category=CardCategory.FRIEND_MILITARY,
        effect_text="被动: 传播文化时+2VP", marker_affair=2, is_friend=True,
    ), owner_player_id="jin_1")]

    jin1_hero = Card(definition=CardDef(
        card_id="hero_j1", name="王导", owner_faction="东晋",
        cost=-1, card_type=CardType.HERO, card_category=CardCategory.HERO_JIN,
        effect_text="", start_order=5, initial_prestige=2, initial_contribution=2,
    ), owner_player_id="jin_1")

    jin_players = [
        PlayerState(player_id="jin_1", faction=FactionType.JIN,
                    military=3, vp=35, prestige=5, contribution=6, order=1,
                    army_reserve_count=12, army_placed_count=3,
                    hand=jin1_hand, hero=jin1_hero, staff_area=jin1_staff,
                    history_area=[]),
        PlayerState(player_id="jin_2", faction=FactionType.JIN,
                    military=2, vp=22, prestige=3, contribution=4, order=3,
                    army_reserve_count=12, army_placed_count=1),
        PlayerState(player_id="jin_3", faction=FactionType.JIN,
                    military=4, vp=28, prestige=4, contribution=5, order=2,
                    army_reserve_count=12, army_placed_count=2),
    ]

    # Court cards
    north_court_card = Card(definition=CardDef(
        card_id="nc1", name="屯田", owner_faction="通用",
        cost=0, card_type=CardType.STRATEGY, card_category=CardCategory.STRATEGY_MILITARY,
        effect_text="+2军力",
    ))
    jin_court_card = Card(definition=CardDef(
        card_id="jc1", name="北伐", owner_faction="通用",
        cost=1, card_type=CardType.STRATEGY, card_category=CardCategory.STRATEGY_MILITARY,
        effect_text="牌组行动: 进军, +1VP",
    ))

    state = GameState(
        round=5, phase=PhaseType.ACTION,
        north_player=north, jin_players=jin_players,
        locations=locs, map_adjacencies=adjs,
        turn_order=["jin_2", "jin_3", "jin_1", "north"],
        active_player_index=0, seed=42,
        north_court=[north_court_card],
        jin_court=[jin_court_card],
        main_deck=[None] * 40,
        main_discard=[Card(definition=CardDef(
            card_id="disc1", name="已弃事件", owner_faction="通用",
            cost=0, card_type=CardType.EVENT, card_category=CardCategory.EVENT_MILITARY,
            effect_text="",
        ))],
    )
    return state


class TestUtils:
    """Utility function tests."""

    def test_card_to_summary(self):
        state = make_full_state()
        card = state.north_player.hand[0]
        summary = card_to_summary(card)
        assert summary["name"] == "北军策略"
        assert summary["cost"] == 1
        assert summary["card_type"] == "strategy"
        assert "card_id" in summary
        assert "markers" in summary

    def test_carddef_to_summary(self):
        state = make_full_state()
        card_def = state.north_player.hand[0].definition
        summary = carddef_to_summary(card_def)
        assert summary["name"] == "北军策略"
        assert summary["is_friend"] is False

    def test_public_player_summary_hides_hand(self):
        state = make_full_state()
        summary = public_player_summary(state.north_player)
        assert summary["hand_count"] == 1
        assert "hand" not in summary

    def test_private_player_summary_has_hand(self):
        state = make_full_state()
        summary = private_player_summary(state.north_player)
        assert "hand" in summary
        assert summary["hand"]["count"] == 1
        assert summary["hand"]["names"] == ["北军策略"]

    def test_full_player_summary_has_all(self):
        state = make_full_state()
        summary = full_player_summary(state.north_player)
        assert "hand" in summary
        assert "vp" in summary
        assert summary["hand_count"] == 1

    def test_location_summary(self):
        state = make_full_state()
        loc = location_summary(state.locations["长安"])
        assert loc["controller"] == "north"
        assert loc["is_fortified"] is True

    def test_deep_freeze(self):
        data = {"a": [1, 2, {"b": 3}], "c": {4, 5}}
        frozen = deep_freeze(data)
        assert isinstance(frozen["a"], tuple)
        assert isinstance(frozen["a"][2], dict)
        assert isinstance(frozen["c"], frozenset)


class TestAdapter:
    """viewport_adapter.py integration tests."""

    def test_create_viewport_for_player_live(self):
        state = make_full_state()
        vp = create_viewport_for_player(state, "north", mode="live")
        assert vp.mode == "live"
        assert vp.viewer_id == "north"

    def test_create_viewport_for_player_snapshot(self):
        state = make_full_state()
        vp = create_viewport_for_player(state, "jin_1", mode="snapshot")
        assert vp.mode == "snapshot"
        assert vp.viewer_id == "jin_1"

    def test_build_snapshot_for_all_players(self):
        state = make_full_state()
        snapshots = build_snapshot_for_all_players(state)
        assert len(snapshots) == 4
        assert "north" in snapshots
        assert "jin_1" in snapshots
        # Each snapshot has private hand info
        assert len(snapshots["north"].get_my_hand()) == 1
        assert len(snapshots["jin_1"].get_my_hand()) == 1
        assert len(snapshots["jin_2"].get_my_hand()) == 0

    def test_build_snapshot_with_actions(self):
        state = make_full_state()
        actions_by_player = {
            "north": [],
            "jin_1": [],
            "jin_2": [],
            "jin_3": [],
        }
        snapshots = build_snapshot_for_all_players(state, actions_by_player)
        assert len(snapshots) == 4

    def test_build_public_snapshot(self):
        state = make_full_state()
        pub = build_public_snapshot(state)
        assert pub["round"] == 5
        assert "长安" in pub["map"]["locations"]
        assert pub["map"]["locations"]["长安"]["is_fortified"] is True
        # No private info in public snapshot
        assert "hand" not in pub["players"]["north"]
        assert pub["players"]["north"]["hand_count"] == 1
        # Decks are counts only
        assert pub["decks"]["main"]["deck_count"] == 40
        assert "已弃事件" in pub["decks"]["main"]["discard"]


class TestCreateViewport:
    """Factory function tests."""

    def test_default_mode_is_live(self):
        state = make_full_state()
        vp = create_viewport(state, "north")
        assert vp.mode == "live"

    def test_explicit_snapshot_mode(self):
        state = make_full_state()
        vp = create_viewport(state, "jin_1", mode="snapshot")
        assert vp.mode == "snapshot"

    def test_available_actions_passed(self):
        state = make_full_state()
        vp = create_viewport(state, "north", [], mode="live")
        assert vp.get_available_actions() == {}


class TestEndToEnd:
    """End-to-end viewport usage scenarios."""

    def test_agent_input_scenario(self):
        """Simulate what an AI agent would receive via SnapshotViewport."""
        state = make_full_state()
        snap = SnapshotViewport.from_state(state, "jin_1")

        # Agent reads its hand
        hand = snap.get_my_hand()
        assert len(hand) == 1
        assert hand[0]["name"] == "东晋密策"

        # Agent reads public state
        north = snap.get_other_player("north")
        assert north["vp"] == 30
        assert north["hand_count"] == 1  # only count, not contents

        # Agent reads map
        locs = snap.get_all_locations()
        assert locs["长安"]["is_fortified"] is True

        # Agent reads tracks
        vp_track = snap.get_vp_track()
        assert isinstance(vp_track, dict)  # VP track exists (may be empty in test)

    def test_cli_query_scenario(self):
        """Simulate CLI query usage."""
        state = make_full_state()
        vp = LiveViewport(state, "north")
        qe = QueryEngine(vp)

        # Interactive query examples
        assert qe.query("my.hand")["names"] == ["北军策略"]
        assert qe.query("my.hand.0")["name"] == "北军策略"
        assert qe.query("my.vp") == 30
        assert qe.query("player.jin_1.prestige") == 5
        assert qe.query("map.长安")["is_fortified"] is True
        assert qe.query("deck.main.count") == 40
        assert "北方" in qe.query("summary")

    def test_cross_viewer_isolation(self):
        """Each viewer sees only their own private info."""
        state = make_full_state()
        snap_north = SnapshotViewport.from_state(state, "north")
        snap_jin1 = SnapshotViewport.from_state(state, "jin_1")
        snap_jin2 = SnapshotViewport.from_state(state, "jin_2")

        # North sees north's hand
        assert len(snap_north.get_my_hand()) == 1
        assert snap_north.get_my_hand()[0]["name"] == "北军策略"

        # Jin1 sees jin1's hand
        assert len(snap_jin1.get_my_hand()) == 1
        assert snap_jin1.get_my_hand()[0]["name"] == "东晋密策"

        # Jin2 sees no hand (empty)
        assert snap_jin2.get_my_hand() == []

        # Public info is consistent
        assert snap_north.get_other_player("jin_1")["vp"] == 35
        assert snap_jin1.get_other_player("jin_1")["vp"] == 35
        assert snap_jin2.get_other_player("jin_1")["vp"] == 35

    def test_viewport_json_full_cycle(self):
        """Build snapshot → serialize → deserialize → verify."""
        state = make_full_state()
        snap = SnapshotViewport.from_state(state, "north")
        json_str = snap.to_json()
        data = json.loads(json_str)

        # Verify key structures survive JSON roundtrip
        assert data["viewer_id"] == "north"
        assert data["round"] == 5
        assert data["public"]["players"]["north"]["hand_count"] == 1
        assert len(data["private"]["hand"]) == 1
        assert data["private"]["hand"][0]["name"] == "北军策略"
