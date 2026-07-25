"""Location and map data models."""

from dataclasses import dataclass, field
from typing import Optional

from .enums import Region, TerrainType, ControlState, CultureType


@dataclass(frozen=True)
class LocationDef:
    """Immutable definition of a map location."""
    location_id: str                        # e.g. "长安", "建康"
    name: str                               # Display name (usually same as location_id)
    region_ids: list[str] = field(default_factory=list)  # Can belong to multiple regions
    culture_slot_available: bool = False    # Whether this location has a culture slot


@dataclass(frozen=True)
class RegionDef:
    """Immutable definition of a map region."""
    region: Region                          # Region enum
    location_ids: list[str]                 # All locations in this region
    control_vp: int = 0                     # VP for controlling this region
    culture_slots: int = 0                  # Number of culture slots (0, 1, or 2)
    initial_culture: Optional[CultureType] = None  # Initial culture marker if any


@dataclass(frozen=True)
class AdjacencyDef:
    """A connection between two locations."""
    location_a: str
    location_b: str
    terrain: TerrainType = TerrainType.SIMPLE

    def connects(self, loc_a: str, loc_b: str) -> bool:
        """Check if this adjacency connects the two locations (order-independent)."""
        return {self.location_a, self.location_b} == {loc_a, loc_b}

    def neighbor_of(self, location_id: str) -> Optional[str]:
        """Return the other end of this connection."""
        if self.location_a == location_id:
            return self.location_b
        if self.location_b == location_id:
            return self.location_a
        return None


@dataclass
class LocationState:
    """Runtime state of a single location on the map."""
    location_id: str
    controller: ControlState = ControlState.NEUTRAL  # Who occupies this
    is_fortified: bool = False                      # 加固标记

    @property
    def is_empty(self) -> bool:
        return self.controller == ControlState.NEUTRAL

    @property
    def is_jin_controlled(self) -> bool:
        return self.controller in (ControlState.JIN_P1, ControlState.JIN_P2,
                                    ControlState.JIN_P3, ControlState.SIMA)

    @property
    def is_north_controlled(self) -> bool:
        return self.controller == ControlState.NORTH

    def is_friendly_to(self, cs: ControlState) -> bool:
        """Check if this location is friendly to the given controller."""
        if cs == ControlState.NORTH:
            return self.controller == ControlState.NORTH
        if cs in (ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3):
            # Friendly to any Jin player or Sima
            return self.is_jin_controlled
        if cs == ControlState.SIMA:
            return self.is_jin_controlled
        return False


@dataclass
class CultureSlot:
    """A culture marker slot in a region. Rulebook §5.1.6."""
    culture: Optional[CultureType] = None
    locked: bool = True   # New markers start locked (背面朝上)


@dataclass
class RegionState:
    """Runtime state of a region."""
    region: Region
    control_marker: Optional[ControlState] = None  # Who holds the control marker
    control_face_up: bool = True                   # Front/back face (背面 = 本回合不结算)
    culture_slots: list[CultureSlot] = field(default_factory=list)

    # ---- culture helpers ----

    def get_cultures(self) -> list[CultureType]:
        """All culture markers currently in this region (excluding empty slots)."""
        return [s.culture for s in self.culture_slots if s.culture is not None]

    def has_culture(self, ct: CultureType) -> bool:
        return any(s.culture == ct for s in self.culture_slots)

    def is_slot_locked(self, ct: CultureType) -> bool:
        for s in self.culture_slots:
            if s.culture == ct:
                return s.locked
        return False

    def place_culture(self, ct: CultureType):
        """Place a marker — fills empty slot or overwrites existing. Always locked."""
        # Try to fill an empty slot first
        for s in self.culture_slots:
            if s.culture is None:
                s.culture = ct
                s.locked = True
                return
        # No empty slot — append
        self.culture_slots.append(CultureSlot(culture=ct, locked=True))

    def remove_culture(self, ct: CultureType):
        """Remove a culture marker from this region."""
        for s in self.culture_slots:
            if s.culture == ct:
                s.culture = None
                s.locked = False
                return

    def flip_culture_lock(self, ct: CultureType):
        """Toggle lock state of a culture marker in this region."""
        for s in self.culture_slots:
            if s.culture == ct:
                s.locked = not s.locked
                return s.locked
        return None

    def unlock_all(self):
        """Unlock all culture markers (settlement phase)."""
        for s in self.culture_slots:
            s.locked = False
