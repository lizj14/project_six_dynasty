"""Area control rules — partial control, full control, and VP rewards.

Rulebook §3.2:
  - 部分控制: 单一玩家 > 控制阈值 → 获得区域控制标记
  - 完全控制: 占据该区域全部地点 → 同时获得部分控制VP
  - 阈值 = floor(区域地点总数 / 2)

For Jin players:
  - Sima + all Jin players' locations count together for Sima control
  - Individual Jin players can also get full control if they alone hold all locations
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass, field
from typing import Optional

from models.enums import ControlState, Region


# Region configuration — loaded from board_info.md
# Format: region -> {partial_vp, full_vp, location_count}
REGION_CONFIG: dict[Region, dict] = {
    Region.XILIANG:   {"partial_vp": 1, "full_vp": 2, "locations": ["张掖","姑臧","金城"],
                        "culture_bonus": None, "initial_culture": "buddhism"},
    Region.GUANZHONG: {"partial_vp": 2, "full_vp": 3, "locations": ["安定","天水","长安"],
                        "culture_bonus": {"type": "vp", "amount": 3}, "initial_culture": None},
    Region.BASHU:     {"partial_vp": 1, "full_vp": 2, "locations": ["汉中","巴郡","蜀郡"],
                        "culture_bonus": {"type": "military", "amount": 1}, "initial_culture": None},
    Region.JINGXIANG: {"partial_vp": 2, "full_vp": 4, "locations": ["襄阳","南郡","巴东","武昌","宛城","上洛"],
                        "culture_bonus": {"type": "draw_card", "amount": 1}, "initial_culture": None},
    Region.JIANGNAN:  {"partial_vp": 3, "full_vp": 5, "locations": ["浔阳","建康","京口","吴","会稽"],
                        "culture_bonus": {"type": "vp", "amount": 3}, "initial_culture": "taoism",
                        "culture_slot_count": 2},  # 江南有两个文化空位
    Region.ZHONGYUAN: {"partial_vp": 6, "full_vp": 8, "locations": ["弘农","洛阳","雍丘","彭城","谯","东平"],
                        "culture_bonus": {"type": "vp", "amount": 2}, "initial_culture": None},
    Region.SHANXI:    {"partial_vp": 1, "full_vp": 2, "locations": ["平阳","太原","上党"],
                        "culture_bonus": {"type": "draw_card", "amount": 1}, "initial_culture": None},
    Region.SHANDONG:  {"partial_vp": 1, "full_vp": 2, "locations": ["济南","广固","琅琊"],
                        "culture_bonus": None, "initial_culture": "confucianism"},
    Region.HUAINAN:   {"partial_vp": 1, "full_vp": 2, "locations": ["寿春","合肥","广陵"],
                        "culture_bonus": {"type": "vp", "amount": 2}, "initial_culture": None},
    Region.HEBEI:     {"partial_vp": 2, "full_vp": 3, "locations": ["中山","襄国","邺城","信都"],
                        "culture_bonus": {"type": "military", "amount": 1}, "initial_culture": None},
    Region.YOUYAN:    {"partial_vp": 0, "full_vp": 1, "locations": ["蓟城","龙城"],
                        "culture_bonus": {"type": "military", "amount": 2}, "initial_culture": None},
    Region.GUANWAI:   {"partial_vp": 0, "full_vp": 1, "locations": ["盛乐","平城"],
                        "culture_bonus": {"type": "military", "amount": 2}, "initial_culture": None},
}


# Region adjacency — used by spread_culture to determine valid target regions.
# Two regions are adjacent if any location in one borders any location in the other
# (derived from map_adjacencies in board data).
REGION_ADJACENCY: dict[Region, set[Region]] = {
    Region.XILIANG:   {Region.GUANZHONG},
    Region.GUANZHONG: {Region.XILIANG, Region.BASHU, Region.JINGXIANG, Region.ZHONGYUAN, Region.SHANXI},
    Region.BASHU:     {Region.GUANZHONG, Region.JINGXIANG},
    Region.JINGXIANG: {Region.GUANZHONG, Region.BASHU, Region.JIANGNAN, Region.ZHONGYUAN, Region.HUAINAN},
    Region.JIANGNAN:  {Region.JINGXIANG, Region.HUAINAN},
    Region.ZHONGYUAN: {Region.GUANZHONG, Region.JINGXIANG, Region.HUAINAN, Region.SHANDONG, Region.HEBEI, Region.SHANXI},
    Region.SHANXI:    {Region.GUANZHONG, Region.ZHONGYUAN, Region.HEBEI, Region.GUANWAI},
    Region.SHANDONG:  {Region.ZHONGYUAN, Region.HEBEI, Region.HUAINAN},
    Region.HUAINAN:   {Region.JINGXIANG, Region.JIANGNAN, Region.ZHONGYUAN, Region.SHANDONG},
    Region.HEBEI:     {Region.ZHONGYUAN, Region.SHANXI, Region.SHANDONG, Region.YOUYAN},
    Region.YOUYAN:    {Region.HEBEI, Region.GUANWAI},
    Region.GUANWAI:   {Region.SHANXI, Region.YOUYAN},
}


def get_adjacent_regions(region: Region) -> set[Region]:
    """Return the set of regions adjacent to the given region."""
    return REGION_ADJACENCY.get(region, set())


@dataclass
class ControlResult:
    """Result of a region control check."""
    region: Region
    partial_controller: Optional[str]   # "north", "jin_1", "jin_2", "jin_3", "sima", None
    full_controller: Optional[str]      # Who has full control (all locations)
    partial_vp: int
    full_vp: int
    threshold: int
    location_count: dict[str, int]      # controller -> count


def check_region_control(state: "GameState", region: Region) -> ControlResult:
    """Check control status for a single region.

    Returns a ControlResult describing who has partial/full control.
    Does NOT award VP — that happens during scoring phases.
    """
    config = REGION_CONFIG.get(region)
    if not config:
        return ControlResult(
            region=region, partial_controller=None, full_controller=None,
            partial_vp=0, full_vp=0, threshold=0, location_count={},
        )

    region_locs = config["locations"]
    total = len(region_locs)
    threshold = total // 2  # floor division

    # Count controllers in this region
    counts: dict[str, int] = {}  # player_id -> count
    for loc_id in region_locs:
        loc = state.locations.get(loc_id)
        if not loc:
            continue
        pid = _control_state_to_player_id(loc.controller)
        if pid:
            counts[pid] = counts.get(pid, 0) + 1

    # --- Partial control check ---
    partial_controller = None

    # Check individual players (exclude sima)
    for pid, count in counts.items():
        if pid == "sima":
            continue
        if count > threshold:
            partial_controller = pid
            break

    # --- Full control check ---
    full_controller = None
    for pid, count in counts.items():
        if pid == "sima":
            continue
        if count == total:
            full_controller = pid
            break

    # --- Sima combined full control (jin+sima = all locations) ---
    # Only applies when no individual has full or partial control.
    if not full_controller and not partial_controller:
        jin_sima_count = sum(
            count for pid, count in counts.items()
            if pid == "sima" or pid.startswith("jin_")
        )
        if jin_sima_count == total:
            full_controller = "sima"
        elif jin_sima_count > threshold:
            partial_controller = "sima"

    # Priority: individual full > individual partial >
    #           sima combined full > sima combined partial > none

    # Update RegionState control_marker so it can be queried later (e.g. by game logger)
    # Initialize RegionState if missing (lazy init)
    if region not in state.regions:
        from models.location import RegionState as RS
        state.regions[region] = RS(region=region)
    rs = state.regions[region]

    # Priority: full controller > partial controller > sima
    if full_controller:
        rs.control_marker = _player_id_to_control_state(full_controller)
    elif partial_controller == "sima":
        rs.control_marker = ControlState.SIMA
    elif partial_controller:
        rs.control_marker = _player_id_to_control_state(partial_controller)
    else:
        rs.control_marker = None

    return ControlResult(
        region=region,
        partial_controller=partial_controller,
        full_controller=full_controller,
        partial_vp=config["partial_vp"],
        full_vp=config["full_vp"],
        threshold=threshold,
        location_count=counts,
    )


def check_all_regions(state: "GameState") -> dict[Region, ControlResult]:
    """Check control for all regions. Returns results keyed by region."""
    return {region: check_region_control(state, region) for region in Region}


def award_region_vp(state: "GameState", results: dict[Region, ControlResult],
                    player_id: str):
    """Award VP to a specific player for regions they control.

    Called during: player's action phase start (rulebook §4.2).
    Only awards VP for face-up control markers.
    """
    player = state.get_player(player_id)
    if not player:
        return

    for region, result in results.items():
        # Full control gives full_vp (NOT partial_vp + full_vp).
        # Rulebook §3.2: 完全控制 = 占据该区域全部地点，获得完全控制VP。
        # Partial control VP is only awarded when the player does NOT have full control.
        if result.full_controller == player_id:
            player.vp += result.full_vp
            state.log_event("area_control_vp", player=player_id,
                            region=region.value, vp=result.full_vp,
                            control_type="full")
        elif result.partial_controller == player_id:
            player.vp += result.partial_vp
            state.log_event("area_control_vp", player=player_id,
                            region=region.value, vp=result.partial_vp,
                            control_type="partial")

        # Check 150 VP trigger
        state.check_vp_game_end(player_id)


def on_location_change(state: "GameState", location_id: str):
    """Called whenever a location's controller changes.

    Updates region control markers and logs the change.
    Full VP awarding happens at the appropriate phase timing.
    """
    # Find which regions this location belongs to
    affected_regions = []
    for region, config in REGION_CONFIG.items():
        if location_id in config["locations"]:
            affected_regions.append(region)

    # Check these regions
    for region in affected_regions:
        result = check_region_control(state, region)
        state.log_event("region_control_check", region=region.value,
                        partial=result.partial_controller,
                        full=result.full_controller,
                        counts=result.location_count)


def _control_state_to_player_id(cs: ControlState) -> Optional[str]:
    """Map ControlState to player_id."""
    mapping = {
        ControlState.NORTH: "north",
        ControlState.JIN_P1: "jin_1",
        ControlState.JIN_P2: "jin_2",
        ControlState.JIN_P3: "jin_3",
        ControlState.SIMA: "sima",
    }
    return mapping.get(cs)


def _player_id_to_control_state(pid: str) -> Optional[ControlState]:
    """Map player_id back to ControlState."""
    mapping = {
        "north": ControlState.NORTH,
        "jin_1": ControlState.JIN_P1,
        "jin_2": ControlState.JIN_P2,
        "jin_3": ControlState.JIN_P3,
        "sima": ControlState.SIMA,
    }
    return mapping.get(pid)
