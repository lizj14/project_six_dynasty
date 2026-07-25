"""LiveViewport — lazy read-only proxy wrapping a live GameState.

Every method builds a fresh filtered copy from the current GameState.
No caching — always reflects the latest state.  No internal references
are ever leaked to the caller.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .interface import Viewport
from .utils import (
    card_to_summary, carddef_to_summary,
    public_player_summary, private_player_summary, full_player_summary,
    location_summary, action_to_summary,
)

if TYPE_CHECKING:
    from models.game_state import GameState
    from engine.actions.base import GameAction


class LiveViewport(Viewport):
    """Lazy read-only proxy wrapping a live GameState.

    Usage:
        vp = LiveViewport(state, "jin_1", available_actions)
        hand = vp.get_my_hand()          # full card details
        public_vp = vp.get_other_player("north")  # only public info
    """

    def __init__(self, state: "GameState", viewer_id: str,
                 available_actions: list["GameAction"] = None):
        self._state = state
        self.viewer_id = viewer_id
        self.mode = "live"
        self._available_actions = list(available_actions) if available_actions else []

    # ================================================================
    # Top-level game info
    # ================================================================

    @property
    def round(self) -> int:
        return self._state.round

    @property
    def phase(self) -> str:
        return self._state.phase.value if hasattr(self._state.phase, 'value') else str(self._state.phase)

    @property
    def turn_order(self) -> list[str]:
        return list(self._state.turn_order)

    @property
    def active_player_index(self) -> int:
        return self._state.active_player_index

    @property
    def game_end_marker(self) -> Optional[str]:
        return self._state.game_end_marker

    @property
    def game_end_reason(self) -> Optional[str]:
        return self._state.game_end_reason

    # ================================================================
    # Player queries
    # ================================================================

    def get_my_player(self) -> dict:
        player = self._state.get_player(self.viewer_id)
        if not player:
            return {}
        return full_player_summary(player, self._state)

    def get_other_player(self, player_id: str) -> dict:
        player = self._state.get_player(player_id)
        if not player:
            return {}
        return public_player_summary(player, self._state)

    def get_all_players_public(self) -> list[dict]:
        return [public_player_summary(p, self._state) for p in self._state.get_all_players()]

    # ================================================================
    # Map / location queries
    # ================================================================

    def get_all_locations(self) -> dict[str, dict]:
        result = {}
        for loc_id, loc in self._state.locations.items():
            result[loc_id] = location_summary(loc, self._state)
        return result

    def get_location(self, location_id: str) -> Optional[dict]:
        loc = self._state.locations.get(location_id)
        if not loc:
            return None
        return location_summary(loc, self._state)

    def get_adjacent_locations(self, location_id: str) -> list[str]:
        return list(self._state.get_adjacent_locations(location_id))

    def get_terrain(self, loc_a: str, loc_b: str) -> Optional[str]:
        t = self._state.get_terrain(loc_a, loc_b)
        if t is None:
            return None
        return t.value if hasattr(t, 'value') else str(t)

    def get_friendly_locations(self) -> list[str]:
        return list(self._state.get_friendly_locations(self.viewer_id))

    def get_regions(self) -> dict[str, dict]:
        from .utils import region_summary
        result = {}
        regions_data = getattr(self._state, 'regions', {})
        for region, rs in self._state.regions.items():
            region_name = region.value if hasattr(region, 'value') else str(region)
            result[region_name] = region_summary(
                region_name, rs, self._state.locations, regions_data,
            )
        return result

    def get_locations_in_region(self, region_name: str) -> list[str]:
        for region, rs in self._state.regions.items():
            rn = region.value if hasattr(region, 'value') else str(region)
            if rn == region_name:
                return list(self._state.get_locations_in_region(region))
        return []

    # ================================================================
    # Court / card zones
    # ================================================================

    def get_court_cards(self, faction: str) -> list[dict]:
        """Return court card summaries.  Court is face-up and public."""
        if faction == "north":
            cards = self._state.north_court
        elif faction == "jin":
            cards = self._state.jin_court
        else:
            return []
        return [card_to_summary(c) for c in cards]

    def get_played_this_round(self, faction: str) -> list[dict]:
        """Return cards played this round by faction.  Public."""
        if faction == "north":
            cards = self._state.north_played_this_round
        elif faction == "jin":
            cards = self._state.jin_played_this_round
        else:
            return []
        return [card_to_summary(c) for c in cards]

    def get_public_actions(self) -> list[dict]:
        return [carddef_to_summary(c.definition) for c in self._state.public_action_pool]

    # ================================================================
    # Track queries
    # ================================================================

    def get_vp_track(self) -> dict[str, int]:
        return dict(self._state.vp_track)

    def get_culture_tracks(self) -> dict[str, dict]:
        result = {}
        for ct, track in self._state.culture_tracks.items():
            ct_name = ct.value if hasattr(ct, 'value') else str(ct)
            result[ct_name] = {
                "supply_level": track.supply_level,
                "map_count": track.map_count,
                "player_contributions": dict(track.player_contributions),
            }
        return result

    def get_prestige_track(self) -> dict[str, int]:
        track = {}
        for p in self._state.jin_players:
            track[p.player_id] = p.prestige
        track["sima"] = self._state.sima.prestige
        return track

    def get_contribution_track(self) -> dict[str, int]:
        track = {}
        for p in self._state.jin_players:
            track[p.player_id] = p.contribution
        return track

    def get_order_track(self) -> dict[str, int]:
        track = {}
        for p in self._state.jin_players:
            track[p.player_id] = p.order
        return track

    # ================================================================
    # Deck queries (counts only — deck contents are hidden)
    # ================================================================

    def get_main_deck_count(self) -> int:
        return len(self._state.main_deck)

    def get_main_discard(self) -> list[str]:
        return [c.name for c in self._state.main_discard]

    def get_national_deck_count(self, faction: str) -> int:
        if faction == "north":
            return len(self._state.north_deck)
        elif faction == "jin":
            return len(self._state.jin_deck)
        return 0

    def get_national_discard(self, faction: str) -> list[str]:
        if faction == "north":
            return [c.name for c in self._state.north_discard]
        elif faction == "jin":
            return [c.name for c in self._state.jin_discard]
        return []

    def get_forced_event_pile_count(self) -> int:
        return len(self._state.forced_event_pile)

    def get_refugee_supply_count(self) -> int:
        return len(self._state.refugee_supply)

    # ================================================================
    # Private info (only for the viewing player)
    # ================================================================

    def get_my_hand(self) -> list[dict]:
        player = self._state.get_player(self.viewer_id)
        if not player:
            return []
        return [card_to_summary(c) for c in player.hand]

    def get_my_staff(self) -> list[dict]:
        player = self._state.get_player(self.viewer_id)
        if not player:
            return []
        return [card_to_summary(c) for c in player.staff_area]

    def get_my_history(self) -> list[dict]:
        player = self._state.get_player(self.viewer_id)
        if not player:
            return []
        return [card_to_summary(c) for c in player.history_area]

    def get_my_hero(self) -> Optional[dict]:
        player = self._state.get_player(self.viewer_id)
        if not player or not player.hero:
            return None
        return card_to_summary(player.hero)

    # ================================================================
    # Emperor / Sima (public)
    # ================================================================

    def get_emperor(self) -> dict:
        emp = self._state.emperor
        emperor_name = ""
        if emp.current_emperor:
            emperor_name = getattr(emp.current_emperor, 'name', '')
        tasks = []
        for t in (emp.active_tasks or []):
            tasks.append({
                "type": t.task_type.value if hasattr(t.task_type, 'value') else str(t.task_type),
                "completed": t.completed,
            })
        return {
            "age": emp.age,
            "emperor_name": emperor_name,
            "prestige": emp.prestige_initial if hasattr(emp, 'prestige_initial') else 0,
            "tasks": tasks,
        }

    def get_sima(self) -> dict:
        sima = self._state.sima
        return {
            "military": sima.military if hasattr(sima, 'military') else 0,
            "vp": sima.vp if hasattr(sima, 'vp') else 0,
            "prestige": sima.prestige if hasattr(sima, 'prestige') else 0,
            "army_placed_count": sima.army_placed_count if hasattr(sima, 'army_placed_count') else 0,
            "army_reserve_count": sima.army_reserve_count if hasattr(sima, 'army_reserve_count') else 0,
            "capital_location": sima.capital_location if hasattr(sima, 'capital_location') else "建康",
        }

    # ================================================================
    # Available actions
    # ================================================================

    def get_available_actions(self) -> dict:
        """Return available actions grouped by category with descriptions.

        Converts GameAction objects to safe ActionSummary dicts.
        """
        player = self._state.get_player(self.viewer_id)
        hand = player.hand if player else []
        court = self._state.get_court_cards(self.viewer_id)
        public = self._state.public_action_pool
        staff = player.staff_area if player else []
        hero = player.hero if player else None

        groups = {
            "quick_actions": [],
            "hand_actions": [],
            "court_actions": [],
            "public_actions": [],
            "activate_actions": [],
            "other_actions": [],
        }

        quick_types = {"march", "occupy", "fortify", "draw", "recruit"}

        for action in self._available_actions:
            atype = getattr(action, 'action_type', '')
            summary = action_to_summary(
                action, self.viewer_id,
                hand_cards=hand, court_cards=court,
                public_cards=public, player_staff=staff,
                player_hero=hero,
            )

            if atype in quick_types:
                groups["quick_actions"].append(summary)
            elif atype == "play_card":
                groups["hand_actions"].append(summary)
            elif atype == "court_action":
                groups["court_actions"].append(summary)
            elif atype == "play_public_card":
                groups["public_actions"].append(summary)
            elif atype == "activate_effect":
                groups["activate_actions"].append(summary)
            else:
                groups["other_actions"].append(summary)

        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    # ================================================================
    # Serialization
    # ================================================================

    def to_dict(self) -> dict:
        """Build a complete viewport dict on-the-fly.

        This constructs the same structure as SnapshotViewport's internal
        dict, but built fresh from the live GameState each call.
        """
        player = self._state.get_player(self.viewer_id)

        # --- Public section ---
        # Map
        locations = self.get_all_locations()
        regions = self.get_regions()

        # Players
        players = {}
        for p in self._state.get_all_players():
            players[p.player_id] = public_player_summary(p, self._state)

        # Court
        court = {
            "north": self.get_court_cards("north"),
            "jin": self.get_court_cards("jin"),
        }
        played_this_round = {
            "north": self.get_played_this_round("north"),
            "jin": self.get_played_this_round("jin"),
        }

        # Public actions
        public_actions = self.get_public_actions()

        # Tracks
        tracks = {
            "vp": self.get_vp_track(),
            "culture": self.get_culture_tracks(),
            "prestige": self.get_prestige_track(),
            "contribution": self.get_contribution_track(),
            "order": self.get_order_track(),
        }

        # Decks
        decks = {
            "main": {"deck_count": self.get_main_deck_count(),
                     "discard": self.get_main_discard()},
            "north": {"deck_count": self.get_national_deck_count("north"),
                      "discard": self.get_national_discard("north")},
            "jin": {"deck_count": self.get_national_deck_count("jin"),
                    "discard": self.get_national_discard("jin")},
        }

        # Emperor / Sima
        emperor = self.get_emperor()
        sima = self.get_sima()

        # Expedition marker location
        expedition_loc = None
        for loc_id, loc in self._state.locations.items():
            if getattr(loc, 'expedition_marker', False):
                expedition_loc = loc_id
                break

        public = {
            "map": {"locations": locations, "regions": regions},
            "players": players,
            "court": court,
            "played_this_round": played_this_round,
            "public_actions": public_actions,
            "tracks": tracks,
            "decks": decks,
            "forced_event_pile_count": self.get_forced_event_pile_count(),
            "refugee_supply_count": self.get_refugee_supply_count(),
            "emperor": emperor,
            "sima": sima,
            "expedition_marker_location": expedition_loc,
        }

        # --- Private section ---
        private = {}
        if player:
            private = private_player_summary(player)
            private["hand"] = self.get_my_hand()
            private["staff"] = self.get_my_staff()
            private["history"] = self.get_my_history()
            private["hero"] = self.get_my_hero()
            # Secret goal is not stored on GameState currently;
            # include placeholder for future use.
            private["secret_goal"] = None

        return {
            "viewer_id": self.viewer_id,
            "mode": "live",
            "round": self.round,
            "phase": self.phase,
            "turn_order": self.turn_order,
            "active_player_index": self.active_player_index,
            "game_end_marker": self.game_end_marker,
            "game_end_reason": self.game_end_reason,
            "public": public,
            "private": private,
            "available_actions": self.get_available_actions(),
        }
