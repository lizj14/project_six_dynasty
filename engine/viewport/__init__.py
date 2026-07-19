"""Viewport system — read-only game state projection with visibility filtering.

Provides three core components:

  Viewport (ABC)       — abstract interface for filtered state views
  LiveViewport         — lazy proxy wrapping a live GameState (engine use)
  SnapshotViewport     — frozen JSON-serializable snapshot (AI input, GUI, replay)
  QueryEngine          — CLI path-based query parser

Usage:
    from viewport import LiveViewport, SnapshotViewport, create_viewport

    # During engine execution:
    vp = LiveViewport(state, "jin_1", available_actions)
    hand = vp.get_my_hand()               # full card details
    public_north = vp.get_other_player("north")  # only public info

    # For AI input / GUI rendering:
    snap = SnapshotViewport.from_state(state, "jin_1", available_actions)
    json_str = snap.to_json()

    # CLI queries:
    vp.query("my.hand")
    vp.query("player.north.vp")
    vp.query("map.all")
"""

from .interface import Viewport
from .live import LiveViewport
from .snapshot import SnapshotViewport
from .query import QueryEngine

__all__ = [
    "Viewport",
    "LiveViewport",
    "SnapshotViewport",
    "QueryEngine",
    "create_viewport",
]


def create_viewport(state: "GameState", viewer_id: str,
                    available_actions: list = None,
                    mode: str = "live") -> Viewport:
    """Factory: create a Viewport for a specific player.

    Args:
        state: Live GameState object.
        viewer_id: Which player's perspective ("north", "jin_1", "jin_2", "jin_3").
        available_actions: Pre-computed list of legal GameAction objects.
        mode: "live" for LiveViewport, "snapshot" for SnapshotViewport.

    Returns:
        A Viewport instance (LiveViewport or SnapshotViewport).
    """
    if mode == "snapshot":
        return SnapshotViewport.from_state(state, viewer_id,
                                           available_actions or [])
    else:
        return LiveViewport(state, viewer_id, available_actions or [])
