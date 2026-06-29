"""Tests for the aggregate GameState model."""

import pytest
from models.enums import PhaseType, ControlState, FactionType, TerrainType
from models.game_state import GameState, SimaState
from models.location import LocationState, AdjacencyDef


class TestGameState:
    """Tests for GameState."""

    def test_get_player(self, minimal_state):
        p = minimal_state.get_player("north")
        assert p is not None
        assert p.faction == FactionType.NORTH

        p = minimal_state.get_player("jin_1")
        assert p is not None
        assert p.faction == FactionType.JIN

    def test_get_player_nonexistent(self, minimal_state):
        assert minimal_state.get_player("ghost") is None

    def test_get_all_players(self, minimal_state):
        players = minimal_state.get_all_players()
        assert len(players) == 4  # 1 north + 3 jin

    def test_get_jin_players(self, minimal_state):
        jin = minimal_state.get_jin_players()
        assert len(jin) == 3

    def test_get_active_player(self, minimal_state):
        active = minimal_state.get_active_player()
        assert active is not None
        assert active.player_id == "north"  # North goes first

    def test_get_location_owner(self, minimal_state):
        assert minimal_state.get_location_owner("长安") == ControlState.NORTH
        assert minimal_state.get_location_owner("弘农") == ControlState.NEUTRAL

    def test_get_adjacent_locations(self, minimal_state):
        neighbors = minimal_state.get_adjacent_locations("长安")
        assert "弘农" in neighbors
        assert "安定" in neighbors
        assert "天水" in neighbors

    def test_is_adjacent(self, minimal_state):
        assert minimal_state.is_adjacent("长安", "弘农")
        assert minimal_state.is_adjacent("弘农", "长安")
        assert not minimal_state.is_adjacent("长安", "洛阳")  # Not directly adjacent

    def test_get_terrain(self, minimal_state):
        from models.enums import TerrainType
        assert minimal_state.get_terrain("长安", "弘农") == TerrainType.DIFFICULT
        assert minimal_state.get_terrain("长安", "安定") == TerrainType.SIMPLE
        assert minimal_state.get_terrain("长安", "洛阳") is None

    def test_get_friendly_locations_north(self, minimal_state):
        friendly = minimal_state.get_friendly_locations("north")
        assert "长安" in friendly  # North controls this
        assert "弘农" not in friendly  # Neutral

    def test_get_friendly_locations_jin(self, minimal_state):
        friendly = minimal_state.get_friendly_locations("jin_1")
        assert "洛阳" in friendly  # Sima controlled => friendly to Jin

    def test_is_friendly_location(self, minimal_state):
        assert minimal_state.is_friendly_location("长安", "north")
        assert not minimal_state.is_friendly_location("长安", "jin_1")
        assert minimal_state.is_friendly_location("洛阳", "jin_1")

    def test_initial_state(self, minimal_state):
        assert minimal_state.round == 1
        assert minimal_state.phase == PhaseType.ACTION
        assert minimal_state.active_player_index == 0

    def test_log_event(self, minimal_state):
        minimal_state.log_event("test_event", detail="test")
        assert len(minimal_state.event_log) == 1
        assert minimal_state.event_log[0]["type"] == "test_event"


class TestSimaState:
    """Tests for Sima NPC state."""

    def test_defaults(self):
        sima = SimaState()
        assert sima.military == 2
        assert sima.vp == 0
        assert sima.prestige == 5
