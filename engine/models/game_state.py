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
                events.append({"type": "forced_event_drawn", "card": card.name,
                               "card_id": card.definition.card_id,
                               "card_text": getattr(card.definition, 'effect_text', '')})

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

    # ======== Value Tracker (功绩/威望 overflow) ========

    def add_contribution(self, player_id: str, amount: int) -> list[dict]:
        """Add contribution with overflow mechanic.

        Cap is 9. When the gain would push past 9, the player caps at 9 and
        for each untaken point, chooses another Jin player to lose 1 功绩.

        Returns events to be merged into the action/effect result.
        """
        from .enums import FactionType as FT
        player = self.get_player(player_id)
        if not player or amount <= 0:
            return []

        events = []
        current = player.contribution
        new_val = current + amount

        if new_val <= 9:
            player.contribution = new_val
            events.append({"type": "contribution_gained", "player": player_id,
                           "amount": amount})
            # Fire on_gain_contribution trigger for passive effects (e.g. 谢安)
            self._fire_contribution_trigger(player_id, amount)
            return events

        # Overflow
        taken = max(0, 9 - current)
        overflow = new_val - 9
        player.contribution = 9
        if taken > 0:
            events.append({"type": "contribution_gained", "player": player_id,
                           "amount": taken})
            self._fire_contribution_trigger(player_id, taken)

        # Get callback from effect resolver
        callback = None
        resolver = getattr(self, 'effect_resolver', None)
        if resolver:
            callback = getattr(resolver, 'select_target_callback', None)

        for i in range(overflow):
            # Find eligible targets: other Jin players with contribution > 0
            targets = [p for p in self.jin_players
                       if p.player_id != player_id and p.contribution > 0]
            if not targets:
                events.append({"type": "contribution_overflow",
                               "overflow": overflow - i,
                               "skipped": True, "reason": "no_valid_targets"})
                break

            if callback:
                prompt = {
                    "type": "overflow_contribution",
                    "title": f"功绩已达上限(9)，选择一个其他玩家使其功绩-1 ({i+1}/{overflow})",
                    "options": [{"id": p.player_id,
                                 "label": f"{p.player_id} (当前功绩:{p.contribution})"}
                                for p in targets],
                }
                chosen = callback(player_id, prompt)
            else:
                chosen = None

            if chosen:
                target = self.get_player(chosen)
                if target and target.contribution > 0:
                    target.contribution -= 1
                    events.append({"type": "contribution_reduced",
                                   "player": chosen, "amount": 1,
                                   "source_player": player_id})
                else:
                    events.append({"type": "contribution_overflow",
                                   "overflow": 1, "skipped": True,
                                   "reason": "target_no_longer_valid"})
            else:
                events.append({"type": "contribution_overflow",
                               "overflow": 1, "skipped": True,
                               "reason": "no_choice"})

        return events

    def _fire_contribution_trigger(self, player_id: str, amount: int):
        """Fire on_gain_contribution trigger for passive effects (e.g. 谢安)."""
        resolver = getattr(self, 'effect_resolver', None)
        if resolver and hasattr(resolver, '_fire_trigger'):
            resolver._fire_trigger("on_gain_contribution", player_id,
                                  {"amount": amount})

    def add_prestige(self, player_id: str, amount: int) -> list[dict]:
        """Add prestige with overflow mechanic.

        Cap is 9. When the gain would push past 9, the player caps at 9 and
        for each untaken point, chooses another player (or 司马家) to lose 1 威望.

        Returns events to be merged into the action/effect result.
        """
        from .enums import FactionType as FT
        player = self.get_player(player_id)
        if not player or amount <= 0:
            return []

        events = []
        current = player.prestige
        new_val = current + amount

        if new_val <= 9:
            player.prestige = new_val
            events.append({"type": "prestige_gained", "player": player_id,
                           "amount": amount})
            return events

        # Overflow
        taken = max(0, 9 - current)
        overflow = new_val - 9
        player.prestige = 9
        if taken > 0:
            events.append({"type": "prestige_gained", "player": player_id,
                           "amount": taken})

        # Get callback from effect resolver
        callback = None
        resolver = getattr(self, 'effect_resolver', None)
        if resolver:
            callback = getattr(resolver, 'select_target_callback', None)

        for i in range(overflow):
            # Eligible targets: other Jin players OR Sima with prestige > 0
            targets = [p for p in self.jin_players
                       if p.player_id != player_id and p.prestige > 0]
            # Sima can also be targeted for prestige
            if self.sima and self.sima.prestige > 0:
                targets.append(self.sima)  # SimaState has prestige and a name

            if not targets:
                events.append({"type": "prestige_overflow",
                               "overflow": overflow - i,
                               "skipped": True, "reason": "no_valid_targets"})
                break

            if callback:
                options = []
                for t in targets:
                    if hasattr(t, 'player_id'):
                        label = f"{t.player_id} (当前威望:{t.prestige})"
                        tid = t.player_id
                    else:
                        # SimaState
                        label = f"司马家 (当前威望:{t.prestige})"
                        tid = "sima"
                    options.append({"id": tid, "label": label})
                prompt = {
                    "type": "overflow_prestige",
                    "title": f"威望已达上限(9)，选择一个目标使其威望-1 ({i+1}/{overflow})",
                    "options": options,
                }
                chosen = callback(player_id, prompt)
            else:
                chosen = None

            if chosen:
                if chosen == "sima":
                    if self.sima and self.sima.prestige > 0:
                        self.sima.prestige -= 1
                        events.append({"type": "prestige_reduced",
                                       "player": "sima", "amount": 1,
                                       "source_player": player_id})
                else:
                    target = self.get_player(chosen)
                    if target and target.prestige > 0:
                        target.prestige -= 1
                        events.append({"type": "prestige_reduced",
                                       "player": chosen, "amount": 1,
                                       "source_player": player_id})
                    else:
                        events.append({"type": "prestige_overflow",
                                       "overflow": 1, "skipped": True,
                                       "reason": "target_no_longer_valid"})
            else:
                events.append({"type": "prestige_overflow",
                               "overflow": 1, "skipped": True,
                               "reason": "no_choice"})

        return events

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
        """Get all locations friendly to a player.

        Friendly locations are used for: fortify, convert, and other
        "friendly territory" checks. For march/occupy adjacency source,
        use get_adjacency_source_locations() instead.
        """
        player = self.get_player(player_id)
        if not player:
            return []
        cs = self._player_control_state(player_id)
        friendly = []
        for loc_id, loc in self.locations.items():
            if loc.is_friendly_to(cs):
                friendly.append(loc_id)
        return friendly

    def get_adjacency_source_locations(self, player_id: str) -> list[str]:
        """Get locations that can serve as adjacency sources for march/occupy/convert.

        Rulebook §3.2: 进军/占据/转化的相邻计算起点:
          - 北方玩家: 仅自己占据的地点
          - 东晋玩家 (正常): 仅自己占据的地点
          - 东晋玩家 (有北伐标记): 自己占据 + 所有友方(含其他东晋+司马家)占据的地点

        Without expedition marker: only own forces. With expedition marker:
        all friendly forces (other Jin players + Sima) count as adjacency sources.
        """
        player = self.get_player(player_id)
        if not player:
            return []
        cs = self._player_control_state(player_id)
        sources = []
        for loc_id, loc in self.locations.items():
            if loc.controller == cs:
                sources.append(loc_id)

        # Expedition marker (北伐): use ALL friendly locations as sources
        # (other Jin players + Sima), not just own + Sima.
        if player.has_expedition_marker and player.faction == FactionType.JIN:
            for loc_id, loc in self.locations.items():
                if loc.is_friendly_to(cs) and loc_id not in sources:
                    sources.append(loc_id)

        return sources

    # ================================================================
    # Passive effect query system
    # ================================================================

    def get_all_passive_sources(self) -> list[tuple["Card", str]]:
        """Collect all in-play cards that may have passive abilities.

        Returns list of (card, owner_player_id).
        Scans: hero, staff_area, history_area, and court (朝堂) of all players.

        Court cards are included because strategy cards (策略牌) with passive
        effects (e.g. 草原部落: on_march → cost -1) are active while in court.
        """
        sources = []
        for player in self.get_all_players():
            pid = player.player_id
            if player.hero:
                sources.append((player.hero, pid))
            for card in player.staff_area:
                sources.append((card, pid))
            for card in player.history_area:
                sources.append((card, pid))

        # Court cards (策略牌) — faction-level, not per-player
        # North court belongs to north player; Jin court is shared by all Jin players
        for card in self.north_court:
            sources.append((card, "north"))
        for card in self.jin_court:
            # Jin court passives affect all Jin players — register under each
            for player in self.get_all_players():
                if player.faction == FactionType.JIN:
                    sources.append((card, player.player_id))

        return sources

    def query_march_cost_reduction(self, player_id: str,
                                   context: dict = None) -> int:
        """Query total march cost reduction from passive sources.

        Scans all in-play passives for march_cost_reduction blocks with
        matching trigger (on_march) that pass scope/filter checks.
        Respects per_turn_limit tracking.

        Returns the total reduction amount (non-negative). The caller
        should apply this as a discount on the base march cost.
        """
        player = self.get_player(player_id)
        if not player:
            return 0

        total_reduction = 0
        for card, owner_id in self.get_all_passive_sources():
            parsed = card.definition.parsed_effect
            if not parsed:
                continue

            for block in parsed.blocks:
                if block.ability_type != "passive":
                    continue
                if block.trigger != "on_march":
                    continue

                # Scope check
                trigger_player = (context or {}).get("player_id", player_id)
                if block.trigger_scope == "self" and trigger_player != owner_id:
                    continue

                # Trigger filter check
                if block.trigger_filter:
                    if not self._match_passive_filter(
                        block.trigger_filter, context or {}):
                        continue

                # Sum reductions from steps
                for step in block.steps:
                    if step.effect_type == "march_cost_reduction":
                        amount = step.params.get("amount", 0)
                        per_turn_limit = step.params.get("per_turn_limit", 999)
                        card_id = card.definition.card_id
                        key = f"{card_id}:march_cost_reduction"
                        used = player.passive_trigger_count.get(key, 0)
                        if used < per_turn_limit:
                            total_reduction += amount

        return total_reduction

    def record_march_cost_reduction_used(self, player_id: str):
        """Increment per-turn counters for all march_cost_reduction passives.

        Called by MarchAction.execute() after applying the cost reduction,
        so that subsequent marches see the updated usage count.
        """
        player = self.get_player(player_id)
        if not player:
            return

        for card, owner_id in self.get_all_passive_sources():
            parsed = card.definition.parsed_effect
            if not parsed:
                continue

            for block in parsed.blocks:
                if block.ability_type != "passive":
                    continue
                if block.trigger != "on_march":
                    continue

                for step in block.steps:
                    if step.effect_type == "march_cost_reduction":
                        per_turn_limit = step.params.get("per_turn_limit", 999)
                        card_id = card.definition.card_id
                        key = f"{card_id}:march_cost_reduction"
                        used = player.passive_trigger_count.get(key, 0)
                        if used < per_turn_limit:
                            player.passive_trigger_count[key] = used + 1

    @staticmethod
    def _match_passive_filter(filter_dict: dict, context: dict) -> bool:
        """Check if event context matches a passive trigger filter."""
        if "marker" in filter_dict:
            marker_type = filter_dict["marker"]
            action = context.get("action")
            if action:
                params = getattr(action, 'params', None) or {}
                card_markers = params.get("markers", {})
                if card_markers.get(marker_type, 0) <= 0:
                    return False
            else:
                return False
        if "card" in filter_dict:
            card_name = filter_dict["card"]
            action = context.get("action")
            if action:
                card_id = getattr(action, 'card_id', '') or ''
                if card_name not in card_id:
                    return False
            else:
                return False
        if "culture" in filter_dict:
            culture_type = filter_dict["culture"]
            action = context.get("action")
            if action:
                params = getattr(action, 'params', None) or {}
                if params.get("culture") != culture_type:
                    return False
            else:
                return False
        return True

    def get_own_locations(self, player_id: str) -> list[str]:
        """Get locations directly controlled by this player (NOT allies).

        Unlike get_friendly_locations(), this only returns locations where
        the controller IS this player's ControlState, not friendly allies.
        """
        cs = self._player_control_state(player_id)
        own = []
        for loc_id, loc in self.locations.items():
            if loc.controller == cs:
                own.append(loc_id)
        return own

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

    def discard_cards(self, player_id: str, cards: list["Card"],
                       target: str = "main", source: str = "hand",
                       reason: str = "") -> list[dict]:
        """Unified card discard — all discard paths go through this method.

        Args:
            player_id: The player discarding (for national discard routing).
            cards: Cards to discard.
            target: "main" → main_discard (shared pile);
                    "national" → faction national discard (north_discard / jin_discard).
            source: "hand", "court", "staff", "deck" — informational for logging.
            reason: Why these cards are being discarded (e.g. "cost", "recruit").

        Returns:
            List of events describing each discard.
        """
        if target == "national":
            pile = self.get_national_discard(player_id)
        else:
            pile = self.main_discard

        events = []
        for card in cards:
            pile.append(card)
            events.append({
                "type": "discard",
                "card": card.name,
                "card_id": card.definition.card_id if card.definition else "",
                "target": target,
                "source": source,
                "reason": reason,
            })
        return events

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
