"""Player state model."""

from dataclasses import dataclass, field
from typing import Optional

from .enums import FactionType, CultureType, MarkerType
from .card import Card


@dataclass
class PlayerState:
    """Runtime state of a single player."""
    player_id: str                          # "north", "jin_1", "jin_2", "jin_3"
    faction: FactionType                    # NORTH or JIN
    hero: Optional[Card] = None             # Currently played hero card (角色牌)
    hand: list[Card] = field(default_factory=list)          # 手牌
    staff_area: list[Card] = field(default_factory=list)   # 幕僚区 (max 3 Jin / 4 North)
    history_area: list[Card] = field(default_factory=list)  # 史书区 (存档区)
    military: int = 0                       # 军力 (resets to 0 at end of action)
    vp: int = 0                             # 胜利点数
    prestige: int = 0                       # 威望 (0-9, Jin only)
    contribution: int = 0                   # 功绩 (0-9, Jin only)
    order: int = 0                          # 行动顺位 position (lower = earlier)
    # Army
    army_reserve_count: int = 0             # 部队储备区 remaining armies
    army_placed_count: int = 0              # Armies currently on the map
    army_reserve_revealed_vp: int = 0       # VP shown on last revealed reserve slot
    army_reserve_revealed_military: int = 0 # Military per turn from reserve
    # Culture
    culture_contributions: dict[CultureType, int] = field(default_factory=lambda: {
        CultureType.CONFUCIANISM: 0,
        CultureType.TAOISM: 0,
        CultureType.BUDDHISM: 0,
    })
    # Markers
    marker_military: int = 0                # 军事标记数
    marker_culture: int = 0                 # 文化标记数
    marker_affair: int = 0                  # 内政标记数
    marker_power: int = 0                   # 权谋标记数
    # Special flags
    has_expedition_marker: bool = False     # 拥有北伐标记
    game_end_marker: bool = False           # 拥有游戏结束标记
    # North-specific
    north_deck: list[Card] = field(default_factory=list)
    north_discard: list[Card] = field(default_factory=list)
    north_court: list[Card] = field(default_factory=list)     # 朝堂区
    north_played: list[Card] = field(default_factory=list)    # 本回合已执行
    # State tracking
    has_taken_hand_action: bool = False     # 已执行手牌行动
    has_taken_court_action: bool = False    # 已执行牌组行动
    has_drawn_quick: bool = False           # 已执行快速摸牌（每回合限1次）
    has_fortified_quick: bool = False       # 已执行快速加固（每回合限1次）

    @property
    def staff_limit(self) -> int:
        """Maximum number of staff (幕僚) cards."""
        return 4 if self.faction == FactionType.NORTH else 3

    @property
    def hand_limit(self) -> int:
        """Maximum hand size at end of action."""
        return 8

    def get_marker(self, marker: MarkerType) -> int:
        """Get the count for a specific marker type."""
        mapping = {
            MarkerType.MILITARY: self.marker_military,
            MarkerType.CULTURE: self.marker_culture,
            MarkerType.AFFAIR: self.marker_affair,
            MarkerType.POWER: self.marker_power,
        }
        return mapping.get(marker, 0)

    def add_marker(self, marker: MarkerType, count: int = 1):
        """Increment a marker count."""
        if marker == MarkerType.MILITARY:
            self.marker_military += count
        elif marker == MarkerType.CULTURE:
            self.marker_culture += count
        elif marker == MarkerType.AFFAIR:
            self.marker_affair += count
        elif marker == MarkerType.POWER:
            self.marker_power += count

    @property
    def total_markers(self) -> int:
        return self.marker_military + self.marker_culture + self.marker_affair + self.marker_power

    @property
    def distinct_markers(self) -> int:
        """Number of distinct marker types with count > 0."""
        return sum(1 for m in MarkerType if self.get_marker(m) > 0)

    @property
    def staff_free_slots(self) -> int:
        return max(0, self.staff_limit - len(self.staff_area))

    def can_play_friend(self) -> bool:
        """Check if there's room for another staff card."""
        return len(self.staff_area) < self.staff_limit

    def can_take_hand_action(self) -> bool:
        """Check if hand action is still available this turn."""
        return not self.has_taken_hand_action

    def can_take_court_action(self) -> bool:
        """Check if court action is still available this turn."""
        return not self.has_taken_court_action

    def reset_action_flags(self):
        """Reset per-turn action tracking at start of player's turn."""
        self.has_taken_hand_action = False
        self.has_taken_court_action = False
        self.has_drawn_quick = False
        self.has_fortified_quick = False

    def end_turn_cleanup(self):
        """Reset military and check hand limit at end of player's turn."""
        self.military = 0
