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
    order: int = 0                          # 行动顺位 position (higher = earlier in turn)
    start_order: int = 0                    # 先动值 (from hero card, immutable during gameplay)
    order_seq: int = 0                      # 到达当前顺位的顺序号 (last-to-arrive = priority)
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
    region_reward_override: Optional[dict] = None  # 区域奖励覆盖 (from 草原部落 etc.)
    # North-specific
    north_deck: list[Card] = field(default_factory=list)
    north_discard: list[Card] = field(default_factory=list)
    north_court: list[Card] = field(default_factory=list)     # 朝堂区
    north_played: list[Card] = field(default_factory=list)    # 本回合已执行
    # State tracking
    has_taken_hand_action: bool = False     # 已执行手牌行动 (第一个)
    hand_action_taken_count: int = 0        # 本回合实际执行的手牌行动次数
    has_taken_court_action: bool = False    # 已执行牌组行动
    court_action_taken_count: int = 0       # 本回合实际执行的牌组行动次数
    extra_court_actions: int = 0            # 由效果授予的额外牌组行动次数
    extra_hand_actions: int = 0             # 由效果授予的额外手牌行动次数
    extra_hand_action_filter: Optional[str] = None  # 额外手牌行动的卡牌类型限制 (e.g. "friend")
    filtered_hand_actions_remaining: int = 0  # 尚未消耗的受限额外手牌行动次数
    has_drawn_quick: bool = False           # 已执行快速摸牌（每回合限1次）
    has_fortified_quick: bool = False       # 已执行快速加固（每回合限1次）
    activated_card_ids: set[str] = field(default_factory=set)  # 本回合已激活过主动效果的卡牌ID
    passive_trigger_count: dict[str, int] = field(default_factory=dict)  # 被动效果每回合触发计数 key="card_id:trigger"

    @property
    def staff_limit(self) -> int:
        """Maximum number of staff (幕僚) cards.

        Base: Jin=3, North=4. Hero cards may override (e.g. 刘裕=5).
        """
        base = 4 if self.faction == FactionType.NORTH else 3
        if self.hero and self.hero.definition:
            hero_limit = self.hero.definition.staff_limit
            if hero_limit and hero_limit > base:
                return hero_limit
        return base

    @property
    def hand_limit(self) -> int:
        """Maximum hand size at end of action."""
        return 8

    def get_marker(self, marker: MarkerType) -> int:
        """Get the count for a specific marker type (static field only)."""
        mapping = {
            MarkerType.MILITARY: self.marker_military,
            MarkerType.CULTURE: self.marker_culture,
            MarkerType.AFFAIR: self.marker_affair,
            MarkerType.POWER: self.marker_power,
        }
        return mapping.get(marker, 0)

    def get_marker_total(self, marker: MarkerType,
                         state: "GameState" = None) -> int:
        """Dynamically compute marker count from all card sources.

        Sums markers from:
        - Static marker field (non-card effects)
        - Hero card definition
        - Staff area cards
        - History area cards
        - Court cards played this turn (rulebook §"卡牌标记")

        Rulebook §"数值归属": markers default to only counting the
        player's own. jin_played_this_round / north_played_this_round
        are shared lists — each card is tagged with _court_played_by.
        """
        total = self.get_marker(marker)

        # Map marker types to CardDef attribute names
        attr_map = {
            MarkerType.MILITARY: 'marker_military',
            MarkerType.CULTURE: 'marker_culture',
            MarkerType.AFFAIR: 'marker_affair',
            MarkerType.POWER: 'marker_power',
        }
        attr = attr_map.get(marker)
        if attr is None:
            return total

        # Hero card
        if self.hero and self.hero.definition:
            total += getattr(self.hero.definition, attr, 0)

        # Staff area
        for card in self.staff_area:
            if card.definition:
                total += getattr(card.definition, attr, 0)

        # History area
        for card in self.history_area:
            if card.definition:
                total += getattr(card.definition, attr, 0)

        # Court cards played this turn — rulebook §"卡牌标记":
        # "计算标记数时，包含朝堂行动选择的牌的标记。"
        # Filter by _court_played_by (rulebook §"数值归属":
        # "默认只计算玩家自己的") — jin_played_this_round is shared.
        if state:
            all_played = (state.north_played_this_round
                          if self.player_id == "north"
                          else state.jin_played_this_round)
            for card in all_played:
                if (getattr(card, '_court_played_by', None) == self.player_id
                        and card.definition):
                    total += getattr(card.definition, attr, 0)

        return total

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
        """Check if hand action is still available this turn.

        A player can take a hand action if:
        - They haven't taken their regular hand action yet, OR
        - They have been granted extra hand actions and haven't used them all.
        """
        limit = 1 + self.extra_hand_actions
        return self.hand_action_taken_count < limit

    def can_take_court_action(self) -> bool:
        """Check if court action is still available this turn.

        A player can take a court action if:
        - They haven't taken their regular court action yet (has_taken_court_action == False), OR
        - They have been granted extra court actions (extra_court_actions > 0) and haven't
          used them all (court_action_taken_count < 1 + extra_court_actions)
        """
        limit = 1 + self.extra_court_actions
        return self.court_action_taken_count < limit

    def reset_action_flags(self):
        """Reset per-turn action tracking at start of player's turn."""
        self.has_taken_hand_action = False
        self.hand_action_taken_count = 0
        self.has_taken_court_action = False
        self.court_action_taken_count = 0
        self.extra_court_actions = 0
        self.extra_hand_actions = 0
        self.extra_hand_action_filter = None
        self.filtered_hand_actions_remaining = 0
        self.has_drawn_quick = False
        self.has_fortified_quick = False
        self.activated_card_ids.clear()
        self.passive_trigger_count.clear()
        self.region_reward_override = None

    def end_turn_cleanup(self):
        """Reset military and check hand limit at end of player's turn."""
        self.military = 0
