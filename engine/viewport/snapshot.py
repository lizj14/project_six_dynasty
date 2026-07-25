"""SnapshotViewport — frozen, JSON-serializable game state snapshot.

Built once from a GameState + viewer_id.  The internal dict is deeply
immutable and JSON-serializable.  Used for AI model input, GUI rendering,
and replay analysis.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .interface import Viewport
from .utils import (
    card_to_summary, carddef_to_summary,
    public_player_summary, private_player_summary,
    location_summary, action_to_summary, deep_freeze,
)

if TYPE_CHECKING:
    from models.game_state import GameState
    from engine.actions.base import GameAction


class SnapshotViewport(Viewport):
    """Frozen, serializable game state snapshot from one player's perspective.

    Usage:
        vp = SnapshotViewport.from_state(state, "jin_1", available_actions)
        json_str = vp.to_json()          # Send to AI / GUI
        hand = vp.get_my_hand()          # Read from frozen data
        data = vp.to_dict()              # Full snapshot dict
    """

    def __init__(self, data: dict):
        self._data = data
        self.viewer_id = data["viewer_id"]
        self.mode = "snapshot"

    @classmethod
    def from_state(cls, state: "GameState", viewer_id: str,
                   available_actions: list["GameAction"] = None) -> "SnapshotViewport":
        """Build a complete snapshot from a live GameState.

        This is the primary factory.  It reads everything once, filters
        by visibility rules, and freezes the result.
        """
        data = _build_snapshot(state, viewer_id, available_actions or [])
        return cls(data)

    # ================================================================
    # Top-level game info
    # ================================================================

    @property
    def round(self) -> int:
        return self._data["round"]

    @property
    def phase(self) -> str:
        return self._data["phase"]

    @property
    def turn_order(self) -> list[str]:
        return list(self._data["turn_order"])

    @property
    def active_player_index(self) -> int:
        return self._data["active_player_index"]

    @property
    def game_end_marker(self) -> Optional[str]:
        return self._data["game_end_marker"]

    @property
    def game_end_reason(self) -> Optional[str]:
        return self._data["game_end_reason"]

    # ================================================================
    # Player queries
    # ================================================================

    def get_my_player(self) -> dict:
        pub = self._data["public"]["players"].get(self.viewer_id, {})
        priv = self._data.get("private", {})
        result = dict(pub)
        result.update(priv)
        return result

    def get_other_player(self, player_id: str) -> dict:
        return dict(self._data["public"]["players"].get(player_id, {}))

    def get_all_players_public(self) -> list[dict]:
        return [dict(v) for v in self._data["public"]["players"].values()]

    # ================================================================
    # Map / location queries
    # ================================================================

    def get_all_locations(self) -> dict[str, dict]:
        return dict(self._data["public"]["map"]["locations"])

    def get_location(self, location_id: str) -> Optional[dict]:
        loc = self._data["public"]["map"]["locations"].get(location_id)
        return dict(loc) if loc else None

    def get_adjacent_locations(self, location_id: str) -> list[str]:
        # Adjacency is not stored in snapshot by default; compute from
        # the map data if available, or return empty.
        # (Map topology is stored in the live GameState but snapshot is
        # a point-in-time data capture.  For full adjacency, use LiveViewport.)
        return []  # Snapshot doesn't store adjacency graph

    def get_terrain(self, loc_a: str, loc_b: str) -> Optional[str]:
        return None  # Snapshot doesn't store terrain graph

    def get_friendly_locations(self) -> list[str]:
        # Compute from snapshot: locations controlled by viewer or their allies
        player = self._data["public"]["players"].get(self.viewer_id, {})
        faction = player.get("faction", "")
        friendly = []
        for loc_id, loc in self._data["public"]["map"]["locations"].items():
            ctrl = loc.get("controller", "")
            if faction == "north" and ctrl == "north":
                friendly.append(loc_id)
            elif faction == "jin" and ctrl in ("jin_p1", "jin_p2", "jin_p3", "jin_1", "jin_2", "jin_3"):
                friendly.append(loc_id)
        return friendly

    def get_regions(self) -> dict[str, dict]:
        return dict(self._data["public"]["map"].get("regions", {}))

    def get_locations_in_region(self, region_name: str) -> list[str]:
        regions = self._data["public"]["map"].get("regions", {})
        for rname, rdata in regions.items():
            if rname == region_name:
                return list(rdata.get("locations", []))
        return []

    # ================================================================
    # Court / card zones
    # ================================================================

    def get_court_cards(self, faction: str) -> list[dict]:
        return [dict(c) for c in self._data["public"]["court"].get(faction, [])]

    def get_played_this_round(self, faction: str) -> list[dict]:
        return [dict(c) for c in self._data["public"]["played_this_round"].get(faction, [])]

    def get_public_actions(self) -> list[dict]:
        return [dict(c) for c in self._data["public"]["public_actions"]]

    # ================================================================
    # Track queries
    # ================================================================

    def get_vp_track(self) -> dict[str, int]:
        return dict(self._data["public"]["tracks"]["vp"])

    def get_culture_tracks(self) -> dict[str, dict]:
        return dict(self._data["public"]["tracks"]["culture"])

    def get_prestige_track(self) -> dict[str, int]:
        return dict(self._data["public"]["tracks"]["prestige"])

    def get_contribution_track(self) -> dict[str, int]:
        return dict(self._data["public"]["tracks"]["contribution"])

    def get_order_track(self) -> dict[str, int]:
        return dict(self._data["public"]["tracks"]["order"])

    # ================================================================
    # Deck queries
    # ================================================================

    def get_main_deck_count(self) -> int:
        return self._data["public"]["decks"]["main"]["deck_count"]

    def get_main_discard(self) -> list[str]:
        return list(self._data["public"]["decks"]["main"]["discard"])

    def get_national_deck_count(self, faction: str) -> int:
        return self._data["public"]["decks"].get(faction, {}).get("deck_count", 0)

    def get_national_discard(self, faction: str) -> list[str]:
        return list(self._data["public"]["decks"].get(faction, {}).get("discard", []))

    def get_forced_event_pile_count(self) -> int:
        return self._data["public"].get("forced_event_pile_count", 0)

    def get_refugee_supply_count(self) -> int:
        return self._data["public"].get("refugee_supply_count", 0)

    # ================================================================
    # Private info
    # ================================================================

    def get_my_hand(self) -> list[dict]:
        return [dict(c) for c in self._data.get("private", {}).get("hand", [])]

    def get_my_staff(self) -> list[dict]:
        return [dict(c) for c in self._data.get("private", {}).get("staff", [])]

    def get_my_history(self) -> list[dict]:
        return [dict(c) for c in self._data.get("private", {}).get("history", [])]

    def get_my_hero(self) -> Optional[dict]:
        hero = self._data.get("private", {}).get("hero")
        return dict(hero) if hero else None

    # ================================================================
    # Emperor / Sima
    # ================================================================

    def get_emperor(self) -> dict:
        return dict(self._data["public"]["emperor"])

    def get_sima(self) -> dict:
        return dict(self._data["public"]["sima"])

    # ================================================================
    # Available actions
    # ================================================================

    def get_available_actions(self) -> dict:
        actions = self._data.get("available_actions", {})
        return {k: [dict(a) for a in v] for k, v in actions.items()}

    # ================================================================
    # Serialization
    # ================================================================

    def to_dict(self) -> dict:
        """Return the frozen snapshot dict (already JSON-serializable)."""
        return self._data


# ================================================================
# Snapshot builder (module-level function)
# ================================================================

def _build_snapshot(state: "GameState", viewer_id: str,
                    available_actions: list["GameAction"]) -> dict:
    """Build a complete snapshot dict from a live GameState.

    This reads everything once, applies visibility filtering, and produces
    a deeply nested dict of primitives.  Called by SnapshotViewport.from_state().
    """
    player = state.get_player(viewer_id)

    # --- Map ---
    locations = {}
    for loc_id, loc in state.locations.items():
        locations[loc_id] = location_summary(loc, state)

    from .utils import region_summary as _region_summary
    regions_data = getattr(state, 'regions', {})
    regions = {}
    for region, rs in state.regions.items():
        region_name = region.value if hasattr(region, 'value') else str(region)
        regions[region_name] = _region_summary(
            region_name, rs, state.locations, regions_data,
        )

    # --- Players (public only) ---
    players = {}
    for p in state.get_all_players():
        players[p.player_id] = public_player_summary(p, state)

    # --- Court ---
    court = {
        "north": [card_to_summary(c) for c in state.north_court],
        "jin": [card_to_summary(c) for c in state.jin_court],
    }
    played_this_round = {
        "north": [card_to_summary(c) for c in state.north_played_this_round],
        "jin": [card_to_summary(c) for c in state.jin_played_this_round],
    }

    # --- Public actions ---
    public_actions_list = [carddef_to_summary(c.definition)
                           for c in state.public_action_pool]

    # --- Tracks ---
    vp_track = dict(state.vp_track)
    culture_tracks = {}
    for ct, track in state.culture_tracks.items():
        ct_name = ct.value if hasattr(ct, 'value') else str(ct)
        culture_tracks[ct_name] = {"supply_level": track.supply_level, "map_count": track.map_count}

    prestige_track = {p.player_id: p.prestige for p in state.jin_players}
    prestige_track["sima"] = state.sima.prestige if hasattr(state.sima, 'prestige') else 0
    contribution_track = {p.player_id: p.contribution for p in state.jin_players}
    order_track = {p.player_id: p.order for p in state.jin_players}

    tracks = {
        "vp": vp_track,
        "culture": culture_tracks,
        "prestige": prestige_track,
        "contribution": contribution_track,
        "order": order_track,
    }

    # --- Decks ---
    decks = {
        "main": {"deck_count": len(state.main_deck),
                 "discard": [c.name for c in state.main_discard]},
        "north": {"deck_count": len(state.north_deck),
                  "discard": [c.name for c in state.north_discard]},
        "jin": {"deck_count": len(state.jin_deck),
                "discard": [c.name for c in state.jin_discard]},
    }

    # --- Emperor / Sima ---
    emp = state.emperor
    emperor = {
        "age": emp.age if hasattr(emp, 'age') else 0,
        "emperor_name": emp.emperor_name if hasattr(emp, 'emperor_name') else "",
        "prestige": emp.prestige if hasattr(emp, 'prestige') else 0,
        "tasks": list(emp.emperor_tasks) if hasattr(emp, 'emperor_tasks') else [],
    }
    sima = state.sima
    sima_data = {
        "military": sima.military if hasattr(sima, 'military') else 0,
        "vp": sima.vp if hasattr(sima, 'vp') else 0,
        "prestige": sima.prestige if hasattr(sima, 'prestige') else 0,
        "army_placed_count": sima.army_placed_count if hasattr(sima, 'army_placed_count') else 0,
        "army_reserve_count": sima.army_reserve_count if hasattr(sima, 'army_reserve_count') else 0,
        "capital_location": sima.capital_location if hasattr(sima, 'capital_location') else "建康",
    }

    # --- Expedition marker location ---
    expedition_loc = None
    for loc_id, loc in state.locations.items():
        if getattr(loc, 'expedition_marker', False):
            expedition_loc = loc_id
            break

    # --- Public section ---
    public = {
        "map": {"locations": locations, "regions": regions},
        "players": players,
        "court": court,
        "played_this_round": played_this_round,
        "public_actions": public_actions_list,
        "tracks": tracks,
        "decks": decks,
        "forced_event_pile_count": len(state.forced_event_pile),
        "refugee_supply_count": len(state.refugee_supply),
        "emperor": emperor,
        "sima": sima_data,
        "expedition_marker_location": expedition_loc,
    }

    # --- Private section ---
    private = {}
    if player:
        private["hand"] = [card_to_summary(c) for c in player.hand]
        private["staff"] = [card_to_summary(c) for c in player.staff_area]
        private["history"] = [card_to_summary(c) for c in player.history_area]
        private["hero"] = card_to_summary(player.hero) if player.hero else None
        private["secret_goal"] = None  # Not yet stored on GameState
        private["can_take_hand_action"] = player.can_take_hand_action()
        private["can_take_court_action"] = player.can_take_court_action()
        private["extra_hand_actions"] = player.extra_hand_actions
        private["extra_court_actions"] = player.extra_court_actions
        private["extra_hand_action_filter"] = player.extra_hand_action_filter
        private["has_drawn_quick"] = player.has_drawn_quick
        private["has_fortified_quick"] = player.has_fortified_quick
        private["has_taken_hand_action"] = player.has_taken_hand_action
        private["has_taken_court_action"] = player.has_taken_court_action
        private["hand_action_taken_count"] = player.hand_action_taken_count
        private["court_action_taken_count"] = player.court_action_taken_count
        private["activated_card_ids"] = list(player.activated_card_ids)
        private["staff_free_slots"] = player.staff_free_slots
        private["staff_limit"] = player.staff_limit
        private["hand_limit"] = player.hand_limit
    else:
        private = {
            "hand": [], "staff": [], "history": [], "hero": None,
            "secret_goal": None,
            "can_take_hand_action": False, "can_take_court_action": False,
            "extra_hand_actions": 0, "extra_court_actions": 0,
            "extra_hand_action_filter": None,
            "has_drawn_quick": False, "has_fortified_quick": False,
            "has_taken_hand_action": False, "has_taken_court_action": False,
            "hand_action_taken_count": 0, "court_action_taken_count": 0,
            "activated_card_ids": [],
            "staff_free_slots": 0, "staff_limit": 3, "hand_limit": 8,
        }

    # --- Available actions ---
    hand = player.hand if player else []
    court_cards = state.get_court_cards(viewer_id)
    staff = player.staff_area if player else []
    hero = player.hero if player else None
    public_cards = state.public_action_pool

    action_groups = {
        "quick_actions": [], "hand_actions": [], "court_actions": [],
        "public_actions": [], "activate_actions": [], "other_actions": [],
    }
    quick_types = {"march", "occupy", "fortify", "draw", "recruit"}

    for action in available_actions:
        atype = getattr(action, 'action_type', '')
        summary = action_to_summary(
            action, viewer_id,
            hand_cards=hand, court_cards=court_cards,
            public_cards=public_cards, player_staff=staff,
            player_hero=hero,
        )
        if atype in quick_types:
            action_groups["quick_actions"].append(summary)
        elif atype == "play_card":
            action_groups["hand_actions"].append(summary)
        elif atype == "court_action":
            action_groups["court_actions"].append(summary)
        elif atype == "play_public_card":
            action_groups["public_actions"].append(summary)
        elif atype == "activate_effect":
            action_groups["activate_actions"].append(summary)
        else:
            action_groups["other_actions"].append(summary)

    available = {k: v for k, v in action_groups.items() if v}

    # --- Assemble ---
    return deep_freeze({
        "viewer_id": viewer_id,
        "mode": "snapshot",
        "round": state.round,
        "phase": state.phase.value if hasattr(state.phase, 'value') else str(state.phase),
        "turn_order": list(state.turn_order),
        "active_player_index": state.active_player_index,
        "game_end_marker": state.game_end_marker,
        "game_end_reason": state.game_end_reason,
        "public": public,
        "private": private,
        "available_actions": available,
    })
