"""Tests for location and map data models."""

import pytest
from models.enums import TerrainType, ControlState, CultureType
from models.location import LocationDef, LocationState, RegionState, AdjacencyDef


class TestAdjacencyDef:
    """Tests for adjacency connections."""

    def test_adjacency_connects(self):
        adj = AdjacencyDef("长安", "弘农", TerrainType.SIMPLE)
        assert adj.connects("长安", "弘农")
        assert adj.connects("弘农", "长安")  # Order independent
        assert not adj.connects("长安", "洛阳")

    def test_neighbor_of(self):
        adj = AdjacencyDef("长安", "弘农")
        assert adj.neighbor_of("长安") == "弘农"
        assert adj.neighbor_of("弘农") == "长安"
        assert adj.neighbor_of("洛阳") is None

    def test_difficult_terrain(self):
        adj = AdjacencyDef("长安", "弘农", TerrainType.DIFFICULT)
        assert adj.terrain == TerrainType.DIFFICULT


class TestLocationState:
    """Tests for runtime location state."""

    def test_default_neutral(self):
        loc = LocationState(location_id="长安")
        assert loc.controller == ControlState.NEUTRAL
        assert not loc.is_fortified
        assert loc.is_empty

    def test_north_controlled(self):
        loc = LocationState(location_id="长安", controller=ControlState.NORTH)
        assert loc.is_north_controlled
        assert not loc.is_jin_controlled
        assert not loc.is_friendly_to(ControlState.JIN_P1)

    def test_jin_controlled(self):
        loc = LocationState(location_id="建康", controller=ControlState.JIN_P1)
        assert loc.is_jin_controlled
        assert not loc.is_north_controlled
        assert loc.is_friendly_to(ControlState.JIN_P2)  # All Jin are friendly
        assert loc.is_friendly_to(ControlState.SIMA)     # Sima is friendly to Jin

    def test_sima_is_jin_friendly(self):
        loc = LocationState(location_id="洛阳", controller=ControlState.SIMA)
        assert loc.is_jin_controlled
        assert loc.is_friendly_to(ControlState.JIN_P1)

    def test_fortified(self):
        loc = LocationState(location_id="长安", is_fortified=True)
        assert loc.is_fortified

    def test_no_culture_on_location(self):
        """Culture markers are regional, not per-location."""
        loc = LocationState(location_id="建康")
        assert not hasattr(loc, 'culture_marker'), "LocationState should not have culture_marker"
        assert not hasattr(loc, 'culture_locked'), "LocationState should not have culture_locked"


class TestLocationDef:
    """Tests for immutable location definitions."""

    def test_create(self):
        loc = LocationDef(
            location_id="长安",
            name="长安",
            region_ids=["关中"],
        )
        assert loc.location_id == "长安"
        assert loc.region_ids == ["关中"]

    def test_multi_region(self):
        """Some locations belong to multiple regions."""
        loc = LocationDef(
            location_id="弘农",
            name="弘农",
            region_ids=["关中", "中原"],
        )
        assert "关中" in loc.region_ids
        assert "中原" in loc.region_ids


class TestRegionState:
    """Tests for region control state."""

    def test_default_no_control(self):
        from models.enums import Region
        rs = RegionState(region=Region.GUANZHONG)
        assert rs.control_marker is None
        assert rs.control_face_up

    def test_culture_slot_place_and_lock(self):
        from models.enums import Region, CultureType
        from models.location import CultureSlot
        rs = RegionState(region=Region.JIANGNAN)
        # Initially no culture
        assert rs.get_cultures() == []
        # Place a marker
        rs.place_culture(CultureType.TAOISM)
        assert rs.has_culture(CultureType.TAOISM)
        assert rs.is_slot_locked(CultureType.TAOISM)  # New markers are locked
        # Unlock
        rs.unlock_all()
        assert not rs.is_slot_locked(CultureType.TAOISM)
        # Flip
        rs.flip_culture_lock(CultureType.TAOISM)
        assert rs.is_slot_locked(CultureType.TAOISM)

    def test_culture_slot_direct(self):
        from models.enums import CultureType
        from models.location import CultureSlot
        slot = CultureSlot()
        assert slot.culture is None
        assert slot.locked is True  # Default locked per §5.1.6
