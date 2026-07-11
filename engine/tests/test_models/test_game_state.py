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


class TestReserveRevealed:
    """Tests for army reserve reveal computation (board_info.md:133-150).

    Rule: VP and military each take the MAX value among all revealed slots.
    """

    def test_zero_placed_returns_zero(self):
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(0, is_north=False)
        assert vp == 0
        assert mil == 0

    def test_negative_placed_returns_zero(self):
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(-5, is_north=False)
        assert vp == 0
        assert mil == 0

    def test_jin_3_placed_no_military_yet(self):
        """Slots 0-2 revealed: (2,0),(4,0),(6,0) → VP max=6, Mil max=0."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(3, is_north=False)
        assert vp == 6
        assert mil == 0

    def test_jin_4_placed_first_military(self):
        """Slots 0-3 revealed: VP max=6, Mil max=1 (slot 3 = 1军力)."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(4, is_north=False)
        assert vp == 6
        assert mil == 1

    def test_jin_5_placed_vp_increases(self):
        """Slots 0-4 revealed: slot 4 = 9vp → VP max=9, Mil max=1."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(5, is_north=False)
        assert vp == 9
        assert mil == 1

    def test_jin_8_placed_two_military(self):
        """Slots 0-7: slot 7 = 2军力 → VP max=13, Mil max=2."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(8, is_north=False)
        assert vp == 13   # max(2,4,6,0,9,11,13,0)
        assert mil == 2   # max(0,0,0,1,0,0,0,2)

    def test_jin_12_placed_three_military(self):
        """Slots 0-11: slot 11 = 3军力 → VP max=20, Mil max=3."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(12, is_north=False)
        assert vp == 20  # max(2,4,6,0,9,11,13,0,16,18,20,0)
        assert mil == 3  # max(0,0,0,1,0,0,0,2,0,0,0,3)

    def test_jin_all_16_placed(self):
        """All 16 slots revealed → VP max=30, Mil max=3."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(16, is_north=False)
        assert vp == 30
        assert mil == 3

    def test_north_28_placed_max_military(self):
        """Slots 0-27: Mil max=7 (slot 27 = 7军力), VP max=48."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(28, is_north=True)
        assert vp == 48  # max VP among first 28 slots
        assert mil == 7  # max military: 1,2,3,4,5,6,7

    def test_north_all_32_placed(self):
        """All 32 slots revealed → VP max=58, Mil max=7."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(32, is_north=True)
        assert vp == 58
        assert mil == 7

    def test_placed_exceeds_track_clamped(self):
        """Placed count beyond track length is clamped."""
        from models.game_state import get_reserve_revealed
        vp, mil = get_reserve_revealed(100, is_north=False)
        assert vp == 30  # max VP of 16-slot track
        assert mil == 3  # max military of 16-slot track
