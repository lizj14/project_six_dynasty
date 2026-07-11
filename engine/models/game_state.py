"""Aggregate GameState model — the complete game snapshot."""

from dataclasses import dataclass, field
from typing import Optional, Any

from .enums import PhaseType, CultureType, Region, ControlState, FactionType
from .card import Card, CardDef
from .player import PlayerState
from .location import LocationState, RegionState, LocationDef, RegionDef, AdjacencyDef


# ================================================================
# 部队储备区露出轨道常量 (board_info.md:133-150)
# ================================================================
# Each slot = (vp, military). Index 0 = first army placed (leftmost slot).
# VP: 终局计分时，取最后一个露出格子的VP值
# Military: 每回合获得军力 = 所有已露出军事格之和

_RESERVE_TRACK_JIN: list[tuple[int, int]] = [
    (2,0), (4,0), (6,0), (0,1), (9,0), (11,0), (13,0), (0,2),
    (16,0), (18,0), (20,0), (0,3), (23,0), (25,0), (27,0), (30,0),
]

_RESERVE_TRACK_NORTH: list[tuple[int, int]] = [
    (2,0), (4,0), (6,0), (0,1), (9,0), (11,0), (13,0), (0,2),
    (16,0), (18,0), (20,0), (0,3), (23,0), (25,0), (27,0), (0,4),
    (30,0), (32,0), (34,0), (0,5), (37,0), (39,0), (41,0), (0,6),
    (44,0), (46,0), (48,0), (0,7), (51,0), (53,0), (55,0), (58,0),
]


def get_reserve_revealed(placed_count: int, is_north: bool = False) -> tuple[int, int]:
    """Compute revealed VP and military from the army reserve track.

    露出规则 (rulebook §3.4): VP和军力各自取当前已露出格子中的最大值。

    Args:
        placed_count: Number of armies placed on the map (taken from reserve).
        is_north: True for North faction (32-slot track), False for Jin/Sima (16-slot).

    Returns:
        (revealed_vp, revealed_military) tuple.
        - revealed_vp: Max VP value among all revealed slots (for end-game scoring).
        - revealed_military: Max military value among all revealed slots (gained each turn).
    """
    track = _RESERVE_TRACK_NORTH if is_north else _RESERVE_TRACK_JIN
    if placed_count <= 0:
        return (0, 0)
    placed = min(placed_count, len(track))
    revealed = track[:placed]
    vp = max((v for v, _ in revealed), default=0)
    military = max((m for _, m in revealed), default=0)
    return (vp, military)


@dataclass
class SimaState:
    """司马家 (Sima clan) NPC faction state."""
    military: int = 2                   # 军力 (0-9)
    vp: int = 0                         # VP
    prestige: int = 5                   # 威望 (0-9), set by emperor card
    army_reserve_count: int = 16        # 部队储备区 (board_info.md)
    army_placed_count: int = 0          # Armies on map
    army_reserve_revealed_vp: int = 0
    army_reserve_revealed_military: int = 0
    is_capital_on_map: bool = True      # 首都标记在地图上


@dataclass
class EmperorState:
    """Current emperor (君主) state."""
    current_emperor: Optional[CardDef] = None  # Current emperor card
    emperor_deck: list[CardDef] = field(default_factory=list)
    age: int = 1                        # 君主年龄轨 position
    active_tasks: list = field(default_factory=list)  # EmperorTask list
    prestige_initial: int = 5           # 起始威望 (from current emperor)


@dataclass
class CultureTrackState:
    """State of one culture track."""
    culture: CultureType
    player_contributions: dict[str, int] = field(default_factory=dict)  # player_id -> level
    supply_level: int = 0               # Current supply level (露出的格子数)
    map_count: int = 0                  # Number of this culture's markers on map


@dataclass
class GameState:
    """Complete game state snapshot. Mutable via action system."""

    # === Round/Phase ===
    round: int = 0                      # 1-10
    phase: PhaseType = PhaseType.SETUP
    active_player_index: int = 0        # Index into turn_order
    turn_order: list[str] = field(default_factory=list)  # Player IDs in action order

    # === Players ===
    north_player: Optional[PlayerState] = None
    jin_players: list[PlayerState] = field(default_factory=list)  # Always 3
    sima: SimaState = field(default_factory=SimaState)

    # === Emperor ===
    emperor: EmperorState = field(default_factory=EmperorState)

    # === Map ===
    locations: dict[str, LocationState] = field(default_factory=dict)
    regions: dict[Region, RegionState] = field(default_factory=dict)
    map_adjacencies: list[AdjacencyDef] = field(default_factory=list)

    # === Card System ===
    main_deck: list[Card] = field(default_factory=list)      # 主版图牌库
    main_discard: list[Card] = field(default_factory=list)   # 主版图弃牌区
    refugee_supply: list[Card] = field(default_factory=list) # 流民供应堆
    forced_event_pile: list[Card] = field(default_factory=list)  # 强制事件牌临时区

    # === National Boards ===
    # Jin national board (shared by all 3 Jin players)
    jin_deck: list[Card] = field(default_factory=list)
    jin_discard: list[Card] = field(default_factory=list)
    jin_court: list[Card] = field(default_factory=list)     # 朝堂区 (10 cards)
    jin_played_this_round: list[Card] = field(default_factory=list)  # 出牌区

    # North national board
    north_deck: list[Card] = field(default_factory=list)
    north_discard: list[Card] = field(default_factory=list)
    north_court: list[Card] = field(default_factory=list)   # 朝堂区 (10 cards)
    north_played_this_round: list[Card] = field(default_factory=list)  # 出牌区

    # === Public Actions ===
    public_actions: list[CardDef] = field(default_factory=list)
    public_action_pool: list["Card"] = field(default_factory=list)    # 5 shared public action cards
    public_exhausted: set[str] = field(default_factory=set)           # card_ids exhausted this round

    # === Culture Tracks ===
    culture_tracks: dict[CultureType, CultureTrackState] = field(default_factory=dict)

    # === Scoring ===
    vp_track: dict[str, int] = field(default_factory=dict)   # player_id + "sima" -> VP
    game_end_marker: Optional[str] = None  # player_id who triggered game end
    game_end_reason: Optional[str] = None  # "150vp", "last_army", "round_10"

    # === Event Log ===
    event_log: list[dict] = field(default_factory=list)

    # === Random Seed ===
    seed: int = 0

    # === Engine-injected dependencies ===
    effect_resolver: Optional[Any] = None
    action_system: Optional[Any] = None

    # === Order tiebreaking (后到者优先) ===
    _order_seq_counter: int = 0             # Global counter for order-change sequencing

    def allocate_order_seq(self) -> int:
        """Return the next order sequence number (for 后到者优先 tiebreaking).

        Called whenever a player's order changes. Later arrivals get higher
        sequence numbers and thus go earlier among players with the same order.
        """
        self._order_seq_counter += 1
        return self._order_seq_counter

    # ======== Card Drawing ========

    def draw_cards(self, player_id: str, count: int = 1) -> list[dict]:
        """通用的摸牌功能。

        处理：
        - 牌库为空时重洗弃牌堆进牌库
        - 摸到强制性事件牌时放入强制事件牌区（不加入手牌）
        - 日志记录

        可在回合开始、行动效果、响应效果等各处复用。
        返回事件列表，每项含 type ("draw" / "forced_event_drawn") 和 card。
        """
        import random as _random
        from .enums import CardType as _CardType

        player = self.get_player(player_id)
        if not player:
            return []

        rng = _random.Random(self.seed + self.round)
        events = []

        for _ in range(count):
            # 牌库空 → 重洗弃牌堆进牌库
            if not self.main_deck:
                if self.main_discard:
                    rng.shuffle(self.main_discard)
                    self.main_deck = self.main_discard
                    self.main_discard = []
                else:
                    break  # 无牌可摸

            if not self.main_deck:
                break

            card = self.main_deck.pop(0)

            # 强制性事件牌 → 立刻结算效果，放入强制事件牌区，不加入手牌
            if card.card_type == _CardType.MECHANISM:
                self.forced_event_pile.append(card)
                events.append({"type": "forced_event_drawn", "card": card.name})

                # 立刻结算强制事件牌效果
                if self.effect_resolver and card.definition.parsed_effect:
                    resolve_result = self.effect_resolver.resolve(
                        card.definition.parsed_effect, self, player_id,
                        context={"source": "forced_event",
                                 "card_id": card.definition.card_id},
                    )
                    events.extend(resolve_result.events)
                    if resolve_result.errors:
                        events.append({"type": "effect_errors",
                                      "errors": resolve_result.errors})
            else:
                player.hand.append(card)
                events.append({"type": "draw", "card": card.name})

            self.log_event("draw", player=player_id, card=card.name)

        return events

    # ======== Helper Methods ========

    def get_player(self, player_id: str) -> Optional[PlayerState]:
        """Get a player state by ID."""
        if self.north_player and self.north_player.player_id == player_id:
            return self.north_player
        for p in self.jin_players:
            if p.player_id == player_id:
                return p
        return None

    def get_all_players(self) -> list[PlayerState]:
        """Get all active players."""
        players = []
        if self.north_player:
            players.append(self.north_player)
        players.extend(self.jin_players)
        return players

    def get_jin_players(self) -> list[PlayerState]:
        return list(self.jin_players)

    def get_active_player(self) -> Optional[PlayerState]:
        """Get the player whose turn it currently is."""
        if self.turn_order and self.active_player_index < len(self.turn_order):
            return self.get_player(self.turn_order[self.active_player_index])
        return None

    def get_location_owner(self, location_id: str) -> ControlState:
        """Get who controls a location."""
        loc = self.locations.get(location_id)
        return loc.controller if loc else ControlState.NEUTRAL

    def get_adjacent_locations(self, location_id: str) -> list[str]:
        """Get all locations adjacent to the given location."""
        neighbors = []
        for adj in self.map_adjacencies:
            nb = adj.neighbor_of(location_id)
            if nb:
                neighbors.append(nb)
        return neighbors

    def get_terrain(self, loc_a: str, loc_b: str) -> Optional['TerrainType']:
        """Get the terrain type between two locations, if they are adjacent."""
        from .enums import TerrainType
        for adj in self.map_adjacencies:
            if adj.connects(loc_a, loc_b):
                return adj.terrain
        return None

    def is_adjacent(self, loc_a: str, loc_b: str) -> bool:
        return self.get_terrain(loc_a, loc_b) is not None

    def get_friendly_locations(self, player_id: str) -> list[str]:
        """Get all locations friendly to a player (considering expedition marker)."""
        player = self.get_player(player_id)
        if not player:
            return []
        cs = self._player_control_state(player_id)
        friendly = []
        for loc_id, loc in self.locations.items():
            if loc.is_friendly_to(cs):
                friendly.append(loc_id)
        # Check expedition marker (北伐) for Jin players
        if player.has_expedition_marker and player.faction == FactionType.JIN:
            for loc_id, loc in self.locations.items():
                if loc.controller in (ControlState.JIN_P1, ControlState.JIN_P2, ControlState.JIN_P3):
                    if loc_id not in friendly:
                        friendly.append(loc_id)
        return friendly

    def is_friendly_location(self, location_id: str, player_id: str) -> bool:
        cs = self._player_control_state(player_id)
        loc = self.locations.get(location_id)
        if not loc:
            return False
        return loc.is_friendly_to(cs)

    def get_locations_in_region(self, region: Region) -> list[str]:
        """Get all location IDs in a region."""
        return [lid for lid, loc in self.locations.items()
                if region.value in loc.location_id  # simple matching; needs region def
                ]

    def _player_control_state(self, player_id: str) -> ControlState:
        """Convert player_id to ControlState for lookup."""
        if player_id == "north":
            return ControlState.NORTH
        elif player_id == "jin_1":
            return ControlState.JIN_P1
        elif player_id == "jin_2":
            return ControlState.JIN_P2
        elif player_id == "jin_3":
            return ControlState.JIN_P3
        elif player_id == "sima":
            return ControlState.SIMA
        return ControlState.NEUTRAL

    def get_court_cards(self, player_id: str) -> list[Card]:
        """Get court cards for the given player's faction (returns the actual list, not a copy)."""
        if player_id == "north":
            return self.north_court
        else:
            return self.jin_court

    def get_national_deck(self, player_id: str) -> list[Card]:
        """Get the national deck for the given player (returns the actual list)."""
        if player_id == "north":
            return self.north_deck
        else:
            return self.jin_deck

    def get_national_discard(self, player_id: str) -> list[Card]:
        """Get the national discard for the given player (returns the actual list)."""
        if player_id == "north":
            return self.north_discard
        else:
            return self.jin_discard

    def log_event(self, event_type: str, **kwargs):
        """Append an event to the game log."""
        self.event_log.append({
            "round": self.round,
            "phase": self.phase.value,
            "type": event_type,
            **kwargs,
        })

    def check_vp_game_end(self, player_id: str, threshold: int = 150) -> bool:
        """Check if a player's VP triggers the game end condition.

        Call this after any VP gain. If the player's VP >= threshold,
        sets game_end_marker and game_end_reason on the state.

        Returns True if game end was triggered (newly or previously).
        """
        if self.game_end_marker:
            return True  # Already triggered
        player = self.get_player(player_id)
        if player and player.vp >= threshold:
            self.game_end_marker = player_id
            self.game_end_reason = "150vp"
            return True
        return False
