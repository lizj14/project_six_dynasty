"""Viewport abstract base class — read-only game state projection.

A Viewport is a *read-only projection* of GameState filtered through a
specific player's visibility rules.  Two modes exist:

  LiveViewport  — lazy proxy wrapping a live GameState (engine use)
  SnapshotViewport — frozen serializable dict (AI input, GUI, replay)

Both implement this ABC, so code that reads from a Viewport works
identically regardless of mode.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class Viewport(ABC):
    """Read-only view of game state from one player's perspective.

    All methods return plain dicts/lists/strings — never expose internal
    Card, GameState, or PlayerState objects.  This prevents agents from
    (a) accidentally mutating game state through returned references, and
    (b) reading hidden information that their player shouldn't see.
    """

    viewer_id: str          # Which player's perspective this is
    mode: str               # "live" or "snapshot"

    # ================================================================
    # Top-level game info
    # ================================================================

    @property
    @abstractmethod
    def round(self) -> int:
        """Current game round (1-10)."""
        ...

    @property
    @abstractmethod
    def phase(self) -> str:
        """Current game phase (e.g. "action", "setup")."""
        ...

    @property
    @abstractmethod
    def turn_order(self) -> list[str]:
        """Player IDs in turn order."""
        ...

    @property
    @abstractmethod
    def active_player_index(self) -> int:
        """Index into turn_order for the currently active player."""
        ...

    @property
    @abstractmethod
    def game_end_marker(self) -> Optional[str]:
        """Player ID who triggered game end, or None."""
        ...

    @property
    @abstractmethod
    def game_end_reason(self) -> Optional[str]:
        """Reason for game end trigger, or None."""
        ...

    # ================================================================
    # Player queries (information visibility enforced here)
    # ================================================================

    @abstractmethod
    def get_my_player(self) -> dict:
        """Return the viewer's own full player state (public + private)."""
        ...

    @abstractmethod
    def get_other_player(self, player_id: str) -> dict:
        """Return *only* public information about another player."""
        ...

    @abstractmethod
    def get_all_players_public(self) -> list[dict]:
        """Return public summaries for all players."""
        ...

    # ================================================================
    # Map / location queries
    # ================================================================

    @abstractmethod
    def get_all_locations(self) -> dict[str, dict]:
        """Return all location summaries.  Map is fully public."""
        ...

    @abstractmethod
    def get_location(self, location_id: str) -> Optional[dict]:
        """Return a single location's summary, or None."""
        ...

    @abstractmethod
    def get_adjacent_locations(self, location_id: str) -> list[str]:
        """Return adjacent location IDs.  Map topology is public."""
        ...

    @abstractmethod
    def get_terrain(self, loc_a: str, loc_b: str) -> Optional[str]:
        """Return terrain type between two locations, or None."""
        ...

    @abstractmethod
    def get_friendly_locations(self) -> list[str]:
        """Return location IDs friendly to the viewer."""
        ...

    @abstractmethod
    def get_regions(self) -> dict[str, dict]:
        """Return all region summaries."""
        ...

    @abstractmethod
    def get_locations_in_region(self, region_name: str) -> list[str]:
        """Return location IDs within a region."""
        ...

    # ================================================================
    # Court / card zones (public face-up cards)
    # ================================================================

    @abstractmethod
    def get_court_cards(self, faction: str) -> list[dict]:
        """Return court card summaries.  Court is face-up and public.

        faction: "north" or "jin"
        """
        ...

    @abstractmethod
    def get_played_this_round(self, faction: str) -> list[dict]:
        """Return cards played this round by faction.  Public.

        faction: "north" or "jin"
        """
        ...

    @abstractmethod
    def get_public_actions(self) -> list[dict]:
        """Return public action card summaries."""
        ...

    # ================================================================
    # Track queries (all tracks are public)
    # ================================================================

    @abstractmethod
    def get_vp_track(self) -> dict[str, int]:
        """Return VP for all players + sima."""
        ...

    @abstractmethod
    def get_culture_tracks(self) -> dict[str, dict]:
        """Return culture track levels and supply."""
        ...

    @abstractmethod
    def get_prestige_track(self) -> dict[str, int]:
        """Return prestige values."""
        ...

    @abstractmethod
    def get_contribution_track(self) -> dict[str, int]:
        """Return contribution values."""
        ...

    @abstractmethod
    def get_order_track(self) -> dict[str, int]:
        """Return order values."""
        ...

    # ================================================================
    # Deck queries (counts only — deck contents are hidden)
    # ================================================================

    @abstractmethod
    def get_main_deck_count(self) -> int:
        """Return count of cards remaining in main deck."""
        ...

    @abstractmethod
    def get_main_discard(self) -> list[str]:
        """Return card names in main discard pile (face-up, public)."""
        ...

    @abstractmethod
    def get_national_deck_count(self, faction: str) -> int:
        """Return count of cards in a national deck.  faction: "north" | "jin"."""
        ...

    @abstractmethod
    def get_national_discard(self, faction: str) -> list[str]:
        """Return card names in a national discard pile (face-up, public)."""
        ...

    @abstractmethod
    def get_forced_event_pile_count(self) -> int:
        """Return count of cards in forced event pile."""
        ...

    @abstractmethod
    def get_refugee_supply_count(self) -> int:
        """Return count of cards in refugee supply."""
        ...

    # ================================================================
    # Private info (only for the viewing player)
    # ================================================================

    @abstractmethod
    def get_my_hand(self) -> list[dict]:
        """Return the viewer's hand cards (full details)."""
        ...

    @abstractmethod
    def get_my_staff(self) -> list[dict]:
        """Return the viewer's staff area cards (full details)."""
        ...

    @abstractmethod
    def get_my_history(self) -> list[dict]:
        """Return the viewer's history area cards (full details)."""
        ...

    @abstractmethod
    def get_my_hero(self) -> Optional[dict]:
        """Return the viewer's hero card summary, or None."""
        ...

    # ================================================================
    # Emperor / Sima (public)
    # ================================================================

    @abstractmethod
    def get_emperor(self) -> dict:
        """Return emperor state summary."""
        ...

    @abstractmethod
    def get_sima(self) -> dict:
        """Return Sima clan state summary."""
        ...

    # ================================================================
    # Available actions (engine-provided)
    # ================================================================

    @abstractmethod
    def get_available_actions(self) -> dict:
        """Return available actions grouped by category with descriptions."""
        ...

    # ================================================================
    # Serialization
    # ================================================================

    @abstractmethod
    def to_dict(self) -> dict:
        """Return a complete dict representation (JSON-serializable).

        LiveViewport builds this on-the-fly.  SnapshotViewport returns
        its internal frozen dict.
        """
        ...

    def to_json(self) -> str:
        """Return JSON string of the full viewport."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    # ================================================================
    # CLI query interface (delegates to QueryEngine at runtime)
    # ================================================================

    def query(self, path: str) -> Any:
        """Execute a path-based query against this viewport.

        Delegates to QueryEngine.  See query.py for path syntax.

        Examples:
          vp.query("my.hand")           → list of card summaries
          vp.query("player.north.vp")   → int
          vp.query("map.all")           → dict of location summaries
          vp.query("tracks.vp")         → dict of VP values
          vp.query("summary")           → one-line viewer state summary
          vp.query("full")              → complete viewport dict
        """
        from .query import QueryEngine
        return QueryEngine(self).query(path)
