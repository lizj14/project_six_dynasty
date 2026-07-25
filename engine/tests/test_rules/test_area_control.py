"""Tests for area control rules."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import ControlState, Region, FactionType, PhaseType
from models.location import LocationState
from models.player import PlayerState
from models.game_state import GameState
from rules.area_control import (
    check_region_control, check_all_regions, ControlResult,
    REGION_CONFIG,
)


def make_state_with_region(region_locations: dict[str, str]):
    """Create a minimal state with controlled locations.

    region_locations: {location_id: controller}
      controller: "north", "jin_1", "jin_2", "jin_3", "sima", "neutral"
    """
    controller_map = {
        "north": ControlState.NORTH,
        "jin_1": ControlState.JIN_P1,
        "jin_2": ControlState.JIN_P2,
        "jin_3": ControlState.JIN_P3,
        "sima": ControlState.SIMA,
        "neutral": ControlState.NEUTRAL,
    }
    locs = {}
    for loc_id, ctrl in region_locations.items():
        locs[loc_id] = LocationState(
            location_id=loc_id,
            controller=controller_map.get(ctrl, ControlState.NEUTRAL),
        )

    state = GameState(
        round=1, phase=PhaseType.ACTION,
        north_player=PlayerState(player_id="north", faction=FactionType.NORTH, army_reserve_count=32),
        jin_players=[
            PlayerState(player_id="jin_1", faction=FactionType.JIN, army_reserve_count=16),
            PlayerState(player_id="jin_2", faction=FactionType.JIN, army_reserve_count=16),
            PlayerState(player_id="jin_3", faction=FactionType.JIN, army_reserve_count=16),
        ],
        locations=locs,
    )
    return state


class TestPartialControl:
    """Tests for partial control (部分控制)."""

    def test_single_player_exceeds_threshold(self):
        """关中: 3 locations, threshold=1. North controls 2 → partial control."""
        state = make_state_with_region({
            "安定": "north", "天水": "north", "长安": "neutral",
        })
        result = check_region_control(state, Region.GUANZHONG)
        assert result.partial_controller == "north"
        assert result.threshold == 1  # 3 // 2
        assert result.partial_vp == 2

    def test_no_one_meets_threshold(self):
        """关中: 3 locations, threshold=1. North=1, Jin_1=1, Jin_2=1.
        Sima+Jin combined = 2 > 1 → Sima partial control (rulebook rule)."""
        state = make_state_with_region({
            "安定": "north", "天水": "jin_1", "长安": "jin_2",
        })
        result = check_region_control(state, Region.GUANZHONG)
        # Sima(0) + Jin_1(1) + Jin_2(1) = 2 > threshold(1)
        assert result.partial_controller == "sima"

    def test_sima_jin_combined(self):
        """Sima + Jin together exceed threshold → Sima gets control."""
        state = make_state_with_region({
            "安定": "sima", "天水": "jin_1", "长安": "north",
        })
        result = check_region_control(state, Region.GUANZHONG)
        # Sima(1) + Jin_1(1) = 2 > threshold(1) → Sima partial control
        assert result.partial_controller == "sima"

    def test_jin_individual_beats_sima(self):
        """Jin_1 alone exceeds threshold → Jin_1 gets control, even with Sima present."""
        state = make_state_with_region({
            "安定": "jin_1", "天水": "jin_1", "长安": "sima",
        })
        result = check_region_control(state, Region.GUANZHONG)
        # Jin_1(2) > threshold(1) → Jin_1, not Sima
        assert result.partial_controller == "jin_1"

    def test_threshold_two_locations(self):
        """幽燕: 2 locations, threshold=1."""
        state = make_state_with_region({
            "蓟城": "north", "龙城": "neutral",
        })
        result = check_region_control(state, Region.YOUYAN)
        # threshold = 2//2 = 1, North has 1 → does NOT exceed threshold (must be >)
        # Actually: control requires count > threshold, 1 is not > 1
        assert result.partial_controller is None

    def test_threshold_two_locations_with_two(self):
        """幽燕: 2 locations, threshold=1. North controls 2 → partial control."""
        state = make_state_with_region({
            "蓟城": "north", "龙城": "north",
        })
        result = check_region_control(state, Region.YOUYAN)
        assert result.partial_controller == "north"


class TestFullControl:
    """Tests for full control (完全控制)."""

    def test_full_control_all_locations(self):
        """Player controls all 3 关中 locations → full control."""
        state = make_state_with_region({
            "安定": "north", "天水": "north", "长安": "north",
        })
        result = check_region_control(state, Region.GUANZHONG)
        assert result.partial_controller == "north"
        assert result.full_controller == "north"
        assert result.full_vp == 3  # partial(2) + full(3) if full control

    def test_full_control_not_with_missing(self):
        """Player controls 2/3 → no full control."""
        state = make_state_with_region({
            "安定": "north", "天水": "north", "长安": "jin_1",
        })
        result = check_region_control(state, Region.GUANZHONG)
        assert result.full_controller is None

    def test_sima_combined_full_control(self):
        """Sima+Jin combined occupying all locations → sima full control."""
        state = make_state_with_region({
            "安定": "sima", "天水": "sima", "长安": "sima",
        })
        result = check_region_control(state, Region.GUANZHONG)
        # Sima combined full control: all locations are sima → full_controller="sima"
        assert result.full_controller == "sima"
        assert result.partial_controller is None


class TestAllRegions:
    """Test checking all regions at once."""

    def test_check_all_returns_all_regions(self):
        state = make_state_with_region({})
        results = check_all_regions(state)
        assert len(results) == len(Region)
        for region in Region:
            assert region in results


class TestVPRegions:
    """Test VP values from board_info.md."""

    def test_zhongyuan_highest_vp(self):
        """中原 should have highest VP: 6/8."""
        cfg = REGION_CONFIG[Region.ZHONGYUAN]
        assert cfg["partial_vp"] == 6
        assert cfg["full_vp"] == 8

    def test_youyan_guanwai_zero_partial(self):
        """幽燕 and 关外 have 0 partial VP."""
        assert REGION_CONFIG[Region.YOUYAN]["partial_vp"] == 0
        assert REGION_CONFIG[Region.GUANWAI]["partial_vp"] == 0

    def test_jiangnan_5_locations(self):
        """江南: 5 locations."""
        assert len(REGION_CONFIG[Region.JIANGNAN]["locations"]) == 5
