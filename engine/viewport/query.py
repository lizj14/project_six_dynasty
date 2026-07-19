"""QueryEngine — path-based query parser for Viewport data.

Syntax: "<namespace>.<key>[.<subkey>...]"

Namespaces:
  my.*          — viewer's own private + public info
  player.<id>.* — public info for a specific player
  player.all    — all players' public info
  map.*         — map / location data
  court.*       — court cards
  tracks.*      — score tracks
  deck.*        — deck counts / discards
  actions.*     — available actions
  emperor       — emperor state
  sima          — Sima state
  round / phase / turn_order  — top-level game info
  summary       — one-line viewer state summary
  full          — complete viewport dict
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .interface import Viewport


class QueryEngine:
    """Parses path strings and routes them to Viewport methods."""

    # ================================================================
    # Zone query helpers (static — usable without a Viewport instance)
    # ================================================================

    @staticmethod
    def _zone_names(items: list) -> dict:
        """Extract {count, names} from a list of summary dicts or Card objects."""
        names = []
        for item in items:
            if isinstance(item, dict):
                names.append(item.get("name", "?"))
            elif hasattr(item, 'name'):
                names.append(item.name)
            else:
                names.append(str(item))
        return {"count": len(items), "names": names}

    @staticmethod
    def _zone_detail(items: list, rest: list[str]) -> Any:
        """Resolve sub-queries on a card zone.

        rest empty     → {count, names}   (lightweight overview)
        rest[0]=detail → full list         (all card summaries)
        rest[0]=N (int)→ single card at N  (drill-down)
        """
        if not rest:
            return QueryEngine._zone_names(items)

        sub = rest[0]
        if sub == "detail":
            return items

        try:
            idx = int(sub)
            if 0 <= idx < len(items):
                return items[idx]
            return {"error": f"索引 {idx} 超出范围 (0-{len(items)-1})"}
        except ValueError:
            return {"error": f"未知子字段: {sub}。可用: detail, 0-{len(items)-1}"}

    def __init__(self, viewport: "Viewport"):
        self._vp = viewport

    def query(self, path: str) -> Any:
        """Parse and execute a query path.

        Returns the requested data or {"error": "..."} on failure.
        """
        path = path.strip().lower()

        # Special queries
        if path == "summary":
            return self._summary()
        if path == "full":
            return self._vp.to_dict()
        if path == "basic":
            return self._basic()
        if path == "round":
            return self._vp.round
        if path == "phase":
            return self._vp.phase
        if path == "turn_order":
            return self._vp.turn_order
        if path == "public_actions":
            return self._vp.get_public_actions()

        parts = path.split(".")
        if not parts:
            return {"error": "empty query"}

        ns = parts[0]
        rest = parts[1:]

        try:
            if ns == "my":
                return self._query_my(rest)
            elif ns == "player":
                return self._query_player(rest)
            elif ns == "map":
                return self._query_map(rest)
            elif ns == "court":
                return self._query_court(rest)
            elif ns == "played":
                return self._query_played(rest)
            elif ns == "tracks":
                return self._query_tracks(rest)
            elif ns in ("deck", "decks"):
                return self._query_deck(rest)
            elif ns == "actions":
                return self._query_actions(rest)
            elif ns == "emperor":
                return self._vp.get_emperor()
            elif ns == "sima":
                return self._vp.get_sima()
            elif ns == "round":
                return self._vp.round
            elif ns == "phase":
                return self._vp.phase
            elif ns == "turn_order":
                return self._vp.turn_order
            elif ns == "public_actions":
                return self._vp.get_public_actions()
            else:
                return {"error": f"unknown namespace: {ns}"}
        except Exception as e:
            return {"error": str(e)}

    # ================================================================
    # Namespace handlers
    # ================================================================

    def _query_my(self, rest: list[str]) -> Any:
        """Handle my.* queries."""
        if not rest:
            return self._vp.get_my_player()

        key = rest[0]
        if key == "hand":
            return self._zone_detail(self._vp.get_my_hand(), rest[1:])
        elif key == "staff":
            return self._zone_detail(self._vp.get_my_staff(), rest[1:])
        elif key == "history":
            return self._zone_detail(self._vp.get_my_history(), rest[1:])
        elif key == "hero":
            return self._vp.get_my_hero()
        elif key == "secret_goal":
            # Not yet stored on GameState
            return None

        # Try numeric fields from get_my_player()
        player = self._vp.get_my_player()
        if key in player:
            return player[key]

        return {"error": f"unknown my.{key}"}

    def _query_player(self, rest: list[str]) -> Any:
        """Handle player.* queries."""
        if not rest:
            return self._vp.get_all_players_public()

        pid = rest[0]
        if pid == "all":
            return self._vp.get_all_players_public()

        if len(rest) == 1:
            # player.<id> — full public summary
            if pid == self._vp.viewer_id:
                return self._vp.get_my_player()
            result = self._vp.get_other_player(pid)
            if not result:
                return {"error": f"player {pid} not found"}
            return result

        # player.<id>.<field>
        if pid == self._vp.viewer_id:
            player = self._vp.get_my_player()
        else:
            player = self._vp.get_other_player(pid)

        if not player:
            return {"error": f"player {pid} not found"}

        field = rest[1]
        if field in player:
            return player[field]
        return {"error": f"unknown field: {field}"}

    def _query_map(self, rest: list[str]) -> Any:
        """Handle map.* queries."""
        if not rest:
            return self._vp.get_all_locations()

        key = rest[0]
        if key == "all":
            return self._vp.get_all_locations()
        elif key == "friendly":
            return self._vp.get_friendly_locations()
        elif key == "regions":
            return self._vp.get_regions()
        elif key == "region" and len(rest) > 1:
            return self._vp.get_locations_in_region(rest[1])
        elif key == "adjacent" and len(rest) > 1:
            return self._vp.get_adjacent_locations(rest[1])
        elif key == "terrain" and len(rest) > 2:
            return self._vp.get_terrain(rest[1], rest[2])
        else:
            # map.<location_id>
            loc = self._vp.get_location(key)
            if loc:
                return loc
            return {"error": f"location {key} not found"}

    def _query_court(self, rest: list[str]) -> Any:
        """Handle court.* queries.  Default: names-only per faction."""
        if not rest:
            return {
                "north": self._zone_names(self._vp.get_court_cards("north")),
                "jin": self._zone_names(self._vp.get_court_cards("jin")),
            }

        faction = rest[0]
        if faction in ("north", "jin"):
            items = self._vp.get_court_cards(faction)
            return self._zone_detail(items, rest[1:])
        return {"error": f"unknown faction: {faction}"}

    def _query_played(self, rest: list[str]) -> Any:
        """Handle played.* queries (cards played this round)."""
        if not rest:
            return {
                "north": self._vp.get_played_this_round("north"),
                "jin": self._vp.get_played_this_round("jin"),
            }
        faction = rest[0]
        if faction in ("north", "jin"):
            return self._vp.get_played_this_round(faction)
        return {"error": f"unknown faction: {faction}"}

    def _query_tracks(self, rest: list[str]) -> Any:
        """Handle tracks.* queries."""
        if not rest:
            return {
                "vp": self._vp.get_vp_track(),
                "culture": self._vp.get_culture_tracks(),
                "prestige": self._vp.get_prestige_track(),
                "contribution": self._vp.get_contribution_track(),
                "order": self._vp.get_order_track(),
            }

        key = rest[0]
        if key == "vp":
            return self._vp.get_vp_track()
        elif key == "culture":
            if len(rest) > 1:
                culture_type = rest[1]
                tracks = self._vp.get_culture_tracks()
                return tracks.get(culture_type, {"error": f"culture type {culture_type} not found"})
            return self._vp.get_culture_tracks()
        elif key == "prestige":
            return self._vp.get_prestige_track()
        elif key == "contribution":
            return self._vp.get_contribution_track()
        elif key == "order":
            return self._vp.get_order_track()
        return {"error": f"unknown track: {key}"}

    def _query_deck(self, rest: list[str]) -> Any:
        """Handle deck.* queries."""
        if not rest:
            return {
                "main": {"count": self._vp.get_main_deck_count(),
                         "discard": self._vp.get_main_discard()},
                "north": {"count": self._vp.get_national_deck_count("north"),
                          "discard": self._vp.get_national_discard("north")},
                "jin": {"count": self._vp.get_national_deck_count("jin"),
                        "discard": self._vp.get_national_discard("jin")},
            }

        key = rest[0]
        if key == "main":
            if len(rest) > 1 and rest[1] == "count":
                return self._vp.get_main_deck_count()
            elif len(rest) > 1 and rest[1] == "discard":
                return self._vp.get_main_discard()
            return {
                "count": self._vp.get_main_deck_count(),
                "discard": self._vp.get_main_discard(),
            }
        elif key in ("north", "jin"):
            if len(rest) > 1 and rest[1] == "count":
                return self._vp.get_national_deck_count(key)
            elif len(rest) > 1 and rest[1] == "discard":
                return self._vp.get_national_discard(key)
            return {
                "count": self._vp.get_national_deck_count(key),
                "discard": self._vp.get_national_discard(key),
            }

        return {"error": f"unknown deck: {key}"}

    def _query_actions(self, rest: list[str]) -> Any:
        """Handle actions.* queries."""
        all_actions = self._vp.get_available_actions()
        if not rest:
            return all_actions

        key = rest[0]
        if key in all_actions:
            return all_actions[key]

        # Map short names
        aliases = {
            "quick": "quick_actions",
            "hand": "hand_actions",
            "court": "court_actions",
            "public": "public_actions",
            "activate": "activate_actions",
            "other": "other_actions",
        }
        mapped = aliases.get(key)
        if mapped and mapped in all_actions:
            return all_actions[mapped]

        return {"error": f"unknown action category: {key}"}

    # ================================================================
    # Summary
    # ================================================================

    def _summary(self) -> str:
        """One-line summary per player — all players, including staff names and history."""
        lines = []
        lines.append(f"=== 第{self._vp.round}回合 {self._vp.phase}阶段 ===")

        # Get all players
        my_id = self._vp.viewer_id
        my_player = self._vp.get_my_player()
        all_public = self._vp.get_all_players_public()

        # Build a combined list: my player + other public players
        players_to_show = []
        if my_player:
            players_to_show.append((my_id, my_player))
        for p in all_public:
            pid = p.get("player_id", "?")
            if pid != my_id:
                players_to_show.append((pid, p))

        for pid, p in players_to_show:
            faction_label = "北方" if p.get("faction") == "north" else "东晋"
            vp = p.get("vp", 0)
            military = p.get("military", 0)
            hand_count = p.get("hand_count", 0)
            army = p.get("army_placed_count", 0)
            staff_names = p.get("staff_names", [])
            history_names = p.get("history_names", [])

            parts = [
                f"[{faction_label}] {pid}",
                f"VP:{vp}",
                f"军力:{military}",
                f"手牌:{hand_count}",
                f"部队:{army}",
            ]

            if p.get("faction") == "jin":
                prestige = p.get("prestige", 0)
                contribution = p.get("contribution", 0)
                order = p.get("order", 0)
                parts.append(f"威望:{prestige}")
                parts.append(f"功绩:{contribution}")
                parts.append(f"顺位:{order}")

            staff_str = " ".join(staff_names) if staff_names else "无"
            parts.append(f"幕僚:[{staff_str}]")

            history_str = " ".join(history_names) if history_names else "无"
            parts.append(f"史书:[{history_str}]")

            lines.append(" | ".join(parts))

        return "\n".join(lines)

    def _basic(self) -> dict:
        """Basic status check for the viewer — hand count, military, VP, markers, locations."""
        return _build_basic_status(self._vp)


# ================================================================
# Basic status query (module-level, usable from HumanPlayer too)
# ================================================================

def _build_basic_status(vp) -> dict:
    """Build a basic status summary respecting viewport visibility."""
    my_info = vp.get_my_player() if hasattr(vp, 'get_my_player') else {}
    all_players = vp.get_all_players_public() if hasattr(vp, 'get_all_players_public') else []

    result = {
        "viewer_id": vp.viewer_id,
        "round": vp.round,
        "phase": vp.phase,
        "turn_order": vp.turn_order,
    }

    # My own full info
    if my_info:
        result["my"] = {
            "hand_count": my_info.get("hand_count", 0),
            "hand_names": my_info.get("hand", {}).get("names", []),
            "military": my_info.get("military", 0),
            "vp": my_info.get("vp", 0),
            "army_placed": my_info.get("army_placed_count", 0),
            "army_reserve": my_info.get("army_reserve_count", 0),
            "staff_names": my_info.get("staff_names", []),
            "history_names": my_info.get("history_names", []),
            "hero": my_info.get("hero", {}).get("name", None) if my_info.get("hero") else None,
        }
        # Jin-specific
        if my_info.get("faction") == "jin":
            result["my"]["prestige"] = my_info.get("prestige", 0)
            result["my"]["contribution"] = my_info.get("contribution", 0)
            result["my"]["order"] = my_info.get("order", 0)

    # Other players (public only)
    result["players"] = {}
    for p in all_players:
        pid = p.get("player_id", "?")
        if pid == vp.viewer_id:
            continue
        result["players"][pid] = {
            "faction": p.get("faction", "?"),
            "hand_count": p.get("hand_count", 0),
            "military": p.get("military", 0),
            "vp": p.get("vp", 0),
            "army_placed": p.get("army_placed_count", 0),
            "army_reserve": p.get("army_reserve_count", 0),
            "staff_names": p.get("staff_names", []),
            "history_names": p.get("history_names", []),
            "hero": p.get("hero", {}).get("name", None) if p.get("hero") else None,
        }
        if p.get("faction") == "jin":
            result["players"][pid]["prestige"] = p.get("prestige", 0)
            result["players"][pid]["contribution"] = p.get("contribution", 0)
            result["players"][pid]["order"] = p.get("order", 0)

    # Friendly locations
    result["friendly_locations"] = vp.get_friendly_locations() if hasattr(vp, 'get_friendly_locations') else []

    return result
