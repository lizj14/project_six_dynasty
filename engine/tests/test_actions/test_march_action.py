"""Tests for March action (进军)."""

import pytest
from models.enums import ControlState, TerrainType, FactionType
from models.location import LocationState, AdjacencyDef
from models.player import PlayerState
from models.game_state import GameState, PhaseType


def make_march_state(north_military=5, target_controller=ControlState.NEUTRAL,
                     fortified=False, terrain=TerrainType.SIMPLE):
    """Create a minimal state for testing march."""
    locs = {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=target_controller,
                              is_fortified=fortified),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
    }
    adjs = [AdjacencyDef("长安", "弘农", terrain), AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE)]

    north = PlayerState(
        player_id="north", faction=FactionType.NORTH,
        military=north_military, vp=0,
        army_reserve_count=8, army_placed_count=1,
    )
    jin1 = PlayerState(
        player_id="jin_1", faction=FactionType.JIN,
        military=1, vp=0, prestige=0,
        army_reserve_count=8, army_placed_count=0,
    )
    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=north, jin_players=[jin1,
            PlayerState(player_id="jin_2", faction=FactionType.JIN, army_reserve_count=8),
            PlayerState(player_id="jin_3", faction=FactionType.JIN, army_reserve_count=8),
        ],
        locations=locs, map_adjacencies=adjs,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0, seed=42,
    )
    # Fix Sima army count: 洛阳 is Sima-controlled
    state.sima.army_placed_count = 1
    state.sima.army_reserve_count = 0  # Override default 16 for test
    return state


class TestMarchValidation:
    """Test march action validation rules."""

    def test_march_valid(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.SIMA)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert result.success, f"Expected valid march, got: {result.error}"

    def test_march_insufficient_military(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(north_military=1, target_controller=ControlState.SIMA)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert not result.success

    def test_march_on_friendly(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.NORTH)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert not result.success

    def test_march_on_neutral(self):
        """Neutral-occupied locations require march first (not occupy)."""
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.NEUTRAL)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.validate(state)
        assert result.success  # Can march on neutral — removes neutral forces

    def test_march_no_adjacent_friendly(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.SIMA)
        action = MarchAction(player_id="north", target_location="洛阳")
        result = action.validate(state)
        assert not result.success  # 洛阳 is adjacent to 弘农 (Sima), not directly to 长安


class TestMarchExecution:
    """Test march action execution."""

    def test_march_basic(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.SIMA)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.execute(state)

        assert result.success, f"March failed: {result.error}"
        # March clears the location → EMPTY (occupy now claims it)
        assert state.locations["弘农"].controller == ControlState.EMPTY
        # Sima lost a unit (returned to reserve)
        assert state.sima.army_placed_count == 0  # was 1, now 0
        assert state.sima.army_reserve_count == 1
        # North paid 3 military
        assert state.north_player.military == 2  # started 5, paid 3
        # North gained 1 VP (march VP, not occupy)
        assert state.north_player.vp == 1
        # North does NOT place an army (occupy handles that)
        # army counts unchanged by march

    def test_march_cost_difficult_terrain(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(north_military=5, target_controller=ControlState.SIMA,
                                  terrain=TerrainType.DIFFICULT)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.execute(state)
        assert result.success
        # Cost: 3 base + 1 difficult = 4
        assert state.north_player.military == 1  # 5 - 4

    def test_march_cost_fortified(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(north_military=5, target_controller=ControlState.SIMA,
                                  fortified=True)
        action = MarchAction(player_id="north", target_location="弘农")
        result = action.execute(state)
        assert result.success
        # Cost: 3 base + 1 fortified = 4
        assert state.north_player.military == 1

    def test_march_removes_fortification(self):
        from engine.actions.quick_actions import MarchAction
        state = make_march_state(target_controller=ControlState.SIMA, fortified=True)
        action = MarchAction(player_id="north", target_location="弘农")
        action.execute(state)
        assert not state.locations["弘农"].is_fortified

    def test_march_jin_gains_prestige(self):
        """Jin player gets 1 prestige for marching on non-friendly."""
        from engine.actions.quick_actions import MarchAction
        # Setup: Jin player at 洛阳 marches on 弘农 (North controlled)
        locs = {
            "洛阳": LocationState(location_id="洛阳", controller=ControlState.JIN_P1),
            "弘农": LocationState(location_id="弘农", controller=ControlState.NORTH),
        }
        adjs = [AdjacencyDef("洛阳", "弘农", TerrainType.SIMPLE)]

        jin1 = PlayerState(
            player_id="jin_1", faction=FactionType.JIN,
            military=5, vp=0, prestige=0,
            army_reserve_count=8, army_placed_count=1,
        )
        north = PlayerState(
            player_id="north", faction=FactionType.NORTH,
            army_reserve_count=8, army_placed_count=1,
        )
        state = GameState(
            round=1, phase=PhaseType.ACTION,
            north_player=north, jin_players=[jin1,
                PlayerState(player_id="jin_2", faction=FactionType.JIN, army_reserve_count=8),
                PlayerState(player_id="jin_3", faction=FactionType.JIN, army_reserve_count=8),
            ],
            locations=locs, map_adjacencies=adjs,
            turn_order=["north", "jin_1", "jin_2", "jin_3"],
        )
        action = MarchAction(player_id="jin_1", target_location="弘农")
        result = action.execute(state)
        assert result.success
        assert jin1.prestige == 1
        assert jin1.vp == 1

    def test_march_minimum_cost(self):
        from engine.actions.quick_actions import MarchAction
        # Give north just 1 military, but test cost calculation
        state = make_march_state(north_military=10, target_controller=ControlState.SIMA,
                                  fortified=True, terrain=TerrainType.DIFFICULT)
        action = MarchAction(player_id="north", target_location="弘农")
        cost = action._calculate_cost(state)
        # 3 base + 1 fortified + 1 difficult = 5
        assert cost == 5
        # Minimum is 1 — test with reductions
        # Isolated would give -1: 3 + 1 + 1 - 1 = 4


class TestMarchEdgeCases:
    """Edge case tests for march."""

    def test_march_game_end_trigger(self):
        """Game end is triggered by OCCUPY (last army placed), not march.

        March no longer places armies — it clears the location to EMPTY.
        The occupy action places the army and triggers game end.
        """
        from engine.actions.quick_actions import MarchAction, OccupyAction
        state = make_march_state(target_controller=ControlState.SIMA)
        state.north_player.army_reserve_count = 1  # One army left in reserve

        # March: clears enemy, gives VP, location → EMPTY
        march = MarchAction(player_id="north", target_location="弘农")
        result = march.execute(state)
        assert result.success
        assert state.locations["弘农"].controller == ControlState.EMPTY
        assert state.game_end_marker is None  # Not triggered by march

        # Occupy: places army, triggers game end
        occupy = OccupyAction(player_id="north", target_location="弘农")
        result = occupy.execute(state)
        assert result.success
        assert state.locations["弘农"].controller == ControlState.NORTH
        assert state.game_end_marker == "north"
        assert state.game_end_reason == "last_army"
