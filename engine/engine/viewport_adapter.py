"""Viewport adapter — bridge between GameEngine and the Viewport system.

This module provides factory functions for creating Viewport instances
during engine execution and for building snapshots for logging/replay.

Usage in GameEngine._run_player_turn():
    from engine.viewport_adapter import create_viewport_for_player

    if self.use_viewport:
        vp = create_viewport_for_player(state, player_id, available)
        action = agent.decide_action(vp, available)
    else:
        action = agent.decide_action(state, available)
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.game_state import GameState
    from engine.actions.base import GameAction
    from viewport.interface import Viewport


def create_viewport_for_player(
    state: "GameState",
    player_id: str,
    available_actions: list["GameAction"] = None,
    mode: str = "live",
) -> "Viewport":
    """Create a Viewport for a specific player.

    Called by GameEngine before passing state to an agent.

    Args:
        state: Live GameState.
        player_id: The player whose perspective to use.
        available_actions: Pre-computed legal actions (for action display).
        mode: "live" for LiveViewport, "snapshot" for SnapshotViewport.

    Returns:
        A Viewport instance.
    """
    from viewport import create_viewport
    return create_viewport(state, player_id, available_actions or [], mode)


def build_snapshot_for_all_players(
    state: "GameState",
    available_actions_by_player: dict[str, list["GameAction"]] = None,
) -> dict[str, "Viewport"]:
    """Build SnapshotViewport instances for all players.

    Useful for logging, replay, or sending state to a GUI that shows
    each player's personal view.

    Args:
        state: Live GameState.
        available_actions_by_player: player_id → list of available actions.

    Returns:
        Dict mapping player_id → SnapshotViewport.
    """
    from viewport import SnapshotViewport

    if available_actions_by_player is None:
        available_actions_by_player = {}

    snapshots = {}
    for player in state.get_all_players():
        pid = player.player_id
        actions = available_actions_by_player.get(pid, [])
        snapshots[pid] = SnapshotViewport.from_state(state, pid, actions)

    return snapshots


def build_public_snapshot(state: "GameState") -> dict:
    """Build a single public-only snapshot (omniscient observer view).

    This shows only information visible to all players — no hand contents,
    no secret goals.  Useful for replay viewing and debugging.

    Args:
        state: Live GameState.

    Returns:
        A dict containing only fully public information.
    """
    from viewport.utils import (
        public_player_summary, location_summary, card_to_summary,
        carddef_to_summary,
    )

    # Map
    locations = {}
    for loc_id, loc in state.locations.items():
        locations[loc_id] = location_summary(loc)

    regions = {}
    for region, rs in state.regions.items():
        region_name = region.value if hasattr(region, 'value') else str(region)
        regions[region_name] = {
            "name": region_name,
            "control_marker": (rs.control_marker.value
                               if rs.control_marker and hasattr(rs.control_marker, 'value')
                               else str(rs.control_marker) if rs.control_marker else None),
        }

    # Players
    players = {}
    for p in state.get_all_players():
        players[p.player_id] = public_player_summary(p)

    # Court
    court = {
        "north": [card_to_summary(c) for c in state.north_court],
        "jin": [card_to_summary(c) for c in state.jin_court],
    }

    # Tracks
    vp_track = dict(state.vp_track)
    culture_tracks = {}
    for ct, track in state.culture_tracks.items():
        ct_name = ct.value if hasattr(ct, 'value') else str(ct)
        culture_tracks[ct_name] = {"supply_level": track.supply_level, "map_count": track.map_count}

    prestige_track = {}
    for p in state.jin_players:
        prestige_track[p.player_id] = p.prestige
    prestige_track["sima"] = state.sima.prestige if hasattr(state.sima, 'prestige') else 0

    contribution_track = {p.player_id: p.contribution for p in state.jin_players}
    order_track = {p.player_id: p.order for p in state.jin_players}

    # Decks (counts only)
    decks = {
        "main": {"deck_count": len(state.main_deck),
                 "discard": [c.name for c in state.main_discard]},
        "north": {"deck_count": len(state.north_deck),
                  "discard": [c.name for c in state.north_discard]},
        "jin": {"deck_count": len(state.jin_deck),
                "discard": [c.name for c in state.jin_discard]},
    }

    # Public actions
    public_actions = [carddef_to_summary(c.definition)
                      for c in state.public_action_pool]

    # Emperor state
    emp = state.emperor
    emperor_name = ""
    if emp.current_emperor:
        emperor_name = getattr(emp.current_emperor, 'name', '')
    emperor_tasks = []
    for t in (emp.active_tasks or []):
        emperor_tasks.append({
            "type": t.task_type.value if hasattr(t.task_type, 'value') else str(t.task_type),
            "completed": t.completed,
        })
    emperor_data = {
        "age": emp.age,
        "emperor_name": emperor_name,
        "prestige": getattr(emp, 'prestige_initial', 0),
        "tasks": emperor_tasks,
    }

    # Sima state
    sima = state.sima
    sima_data = {
        "military": sima.military if hasattr(sima, 'military') else 0,
        "vp": sima.vp if hasattr(sima, 'vp') else 0,
        "prestige": sima.prestige if hasattr(sima, 'prestige') else 0,
        "army_placed_count": sima.army_placed_count if hasattr(sima, 'army_placed_count') else 0,
    }

    return {
        "round": state.round,
        "phase": state.phase.value if hasattr(state.phase, 'value') else str(state.phase),
        "turn_order": list(state.turn_order),
        "active_player_index": state.active_player_index,
        "map": {"locations": locations, "regions": regions},
        "players": players,
        "court": court,
        "tracks": {
            "vp": vp_track,
            "culture": culture_tracks,
            "prestige": prestige_track,
            "contribution": contribution_track,
            "order": order_track,
        },
        "decks": decks,
        "public_actions": public_actions,
        "emperor": emperor_data,
        "sima": sima_data,
        "game_end_marker": state.game_end_marker,
        "game_end_reason": state.game_end_reason,
    }
