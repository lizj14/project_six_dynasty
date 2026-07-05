"""Tests for usurp and sima modules."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import FactionType, PhaseType
from models.player import PlayerState
from models.game_state import GameState
from rules.usurp import can_usurp, can_usurp_with_tie
from rules.sima import distribute_sima_military, can_place_sima_army


def make_state(north_prestige=0, jin1_pres=0, jin2_pres=0, jin3_pres=0,
               sima_pres=5, sima_military=6):
    """Create a state for usurp/sima tests."""
    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=PlayerState(player_id="north", faction=FactionType.NORTH),
        jin_players=[
            PlayerState(player_id="jin_1", faction=FactionType.JIN,
                         prestige=jin1_pres),
            PlayerState(player_id="jin_2", faction=FactionType.JIN,
                         prestige=jin2_pres),
            PlayerState(player_id="jin_3", faction=FactionType.JIN,
                         prestige=jin3_pres),
        ],
    )
    state.sima.prestige = sima_pres
    state.sima.military = sima_military
    return state


class TestUsurp:
    """Tests for usurp (僭越) judgment."""

    def test_usurp_highest_prestige(self):
        """Jin1 has 6 > others(3,3) and > Sima(5) → can usurp."""
        state = make_state(jin1_pres=6, jin2_pres=3, jin3_pres=3, sima_pres=5)
        assert can_usurp(state, "jin_1")

    def test_usurp_tied_with_jin(self):
        """Jin1 tied with Jin2 → cannot usurp."""
        state = make_state(jin1_pres=6, jin2_pres=6, jin3_pres=3, sima_pres=5)
        assert not can_usurp(state, "jin_1")

    def test_usurp_lower_than_sima(self):
        """Jin1 < Sima → cannot usurp."""
        state = make_state(jin1_pres=4, sima_pres=5)
        assert not can_usurp(state, "jin_1")

    def test_usurp_tied_with_sima(self):
        """Jin1 tied with Sima → cannot usurp (standard rules)."""
        state = make_state(jin1_pres=5, jin2_pres=3, jin3_pres=3, sima_pres=5)
        assert not can_usurp(state, "jin_1")

    def test_usurp_with_tie_allows_sima_tie(self):
        """With tie allowed (王敦), tied with Sima → can usurp."""
        state = make_state(jin1_pres=5, jin2_pres=3, jin3_pres=3, sima_pres=5)
        assert can_usurp_with_tie(state, "jin_1")

    def test_north_cannot_usurp(self):
        """North player can never usurp."""
        state = make_state()
        assert not can_usurp(state, "north")


class TestSimaMilitary:
    """Tests for Sima military distribution."""

    def test_distribute_excess(self):
        """Sima military=8 (>6) → distribute, each Jin +1, Sima -3."""
        state = make_state(sima_military=8)
        for p in state.jin_players:
            p.military = 0
        events = distribute_sima_military(state)
        assert state.sima.military == 5  # 8 - 3
        for p in state.jin_players:
            assert p.military == 1

    def test_distribute_multiple_rounds(self):
        """Sima military=13 (>6) → distribute twice."""
        state = make_state(sima_military=13)
        for p in state.jin_players:
            p.military = 0
        distribute_sima_military(state)
        # Round 1: 13-3=10, still >6
        # Round 2: 10-3=7, still >6? Actually wait:
        # 13 → -3 → 10, still >6
        # 10 → -3 → 7, still >6
        # 7  → -3 → 4, ≤6 → stop
        assert state.sima.military == 4
        for p in state.jin_players:
            assert p.military == 3  # 3 rounds × 1

    def test_no_distribute_below_6(self):
        """Sima military ≤ 6 → no distribution."""
        state = make_state(sima_military=5)
        for p in state.jin_players:
            p.military = 0
        distribute_sima_military(state)
        assert state.sima.military == 5
        for p in state.jin_players:
            assert p.military == 0

    def test_can_place_sima_army(self):
        """Sima has military and reserve → can place."""
        state = make_state(sima_military=3)
        state.sima.army_reserve_count = 10
        assert can_place_sima_army(state)

    def test_cannot_place_no_military(self):
        """Sima military=0 → cannot place."""
        state = make_state(sima_military=0)
        state.sima.army_reserve_count = 10
        assert not can_place_sima_army(state)
