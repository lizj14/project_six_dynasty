"""Card data models — CardDef (immutable definition) and Card (runtime instance)."""

from dataclasses import dataclass, field
from typing import Optional

from .enums import CardType, CardCategory, FactionType, MarkerType, CultureType


@dataclass(frozen=True)
class CardDef:
    """Immutable card definition loaded from CSV. Never changes during play.

    This is the canonical representation of a card's static data.
    The runtime Card class wraps this with ownership and location info.
    """
    card_id: str                           # Unique identifier, e.g. "initial_士兵_1"
    name: str                              # 卡牌名称
    owner_faction: str                     # 归属: 苻坚, 王导, 初始, 北方, 通用, etc.
    cost: int                              # 费用 (0-3; -1 for hero/emperor/goal cards)
    card_type: CardType                    # 角色牌/事件牌/策略牌/幕僚牌/强制事件牌/...
    card_category: CardCategory            # Fine-grained category
    effect_text: str                       # Raw effect text (templated Chinese)
    resource_vp: int = 0                   # VP production (per-turn or one-time)
    resource_military: int = 0             # Military production
    history_vp: int = 0                    # 史书vp (scored when archived)
    marker_military: int = 0               # 军事标记 count
    marker_culture: int = 0                # 文化标记 count
    marker_affair: int = 0                 # 内政标记 count
    marker_power: int = 0                  # 权谋标记 count
    faction_restriction: Optional[str] = None  # "jin" | "north" | None
    is_usurp: bool = False                 # 僭越 effect
    is_public: bool = False                # 公共行动牌
    culture_confucianism: int = 0          # 儒学 contribution
    culture_taoism: int = 0                # 玄学 contribution
    culture_buddhism: int = 0              # 佛学 contribution
    # For hero cards
    start_order: int = 0                   # 先动值 (initial turn order, higher=earlier)
    initial_contribution: int = 0          # 初始功绩
    initial_prestige: int = 0              # 初始威望
    initial_order: int = 1                 # 初始顺位 (default 1 if enter doesn't change)
    staff_limit: int = 3                   # 幕僚区上限 (Jin=3, North=4, 刘裕=5)
    # For emperor cards
    initial_prestige: int = 0              # 初始威望
    emperor_tasks: list[str] = field(default_factory=list)  # 君主骰任务面
    # For goal cards
    goal_simple_vp: int = 0                # VP for easy condition
    goal_full_vp: int = 0                  # VP for hard condition
    goal_simple_condition: str = ""        # Easy condition text
    goal_full_condition: str = ""          # Hard condition text
    # For friend cards
    is_friend: bool = False                # True if this is a 幕僚牌
    # For strategy cards — resource option when in court
    resource_option_army: int = 0          # 军力 from resource option
    resource_option_vp: int = 0            # VP from resource option
    # Pre-parsed effect AST (populated at load time, never regex at runtime)
    parsed_effect: Optional["CardEffect"] = None

    # ======== AST-based queries (no regex at runtime) ========

    @property
    def has_strategy_action(self) -> bool:
        """Does this card have a court action effect (行动：)?"""
        if not self.parsed_effect:
            return False
        from cards.effect_ast import AbilityType
        return any(b.ability_type == AbilityType.STRATEGY_ACTION
                   for b in self.parsed_effect.blocks)

    @property
    def has_enter_effect(self) -> bool:
        """Does this card have a hero enter effect (登场：)?"""
        if not self.parsed_effect:
            return False
        from cards.effect_ast import AbilityType
        return any(b.ability_type == AbilityType.ENTER
                   for b in self.parsed_effect.blocks)

    @property
    def has_active_ability(self) -> bool:
        if not self.parsed_effect:
            return False
        from cards.effect_ast import AbilityType
        return any(b.ability_type == AbilityType.ACTIVE
                   for b in self.parsed_effect.blocks)

    @property
    def has_passive_ability(self) -> bool:
        if not self.parsed_effect:
            return False
        from cards.effect_ast import AbilityType
        return any(b.ability_type == AbilityType.PASSIVE
                   for b in self.parsed_effect.blocks)

    @property
    def has_forced_effect(self) -> bool:
        if not self.parsed_effect:
            return False
        from cards.effect_ast import AbilityType
        return any(b.ability_type == AbilityType.FORCED
                   for b in self.parsed_effect.blocks)

    @property
    def markers(self) -> dict[MarkerType, int]:
        """Return all non-zero marker counts."""
        result = {}
        if self.marker_military > 0:
            result[MarkerType.MILITARY] = self.marker_military
        if self.marker_culture > 0:
            result[MarkerType.CULTURE] = self.marker_culture
        if self.marker_affair > 0:
            result[MarkerType.AFFAIR] = self.marker_affair
        if self.marker_power > 0:
            result[MarkerType.POWER] = self.marker_power
        return result

    @property
    def culture_tags(self) -> dict[CultureType, int]:
        """Return all non-zero culture contributions."""
        result = {}
        if self.culture_confucianism > 0:
            result[CultureType.CONFUCIANISM] = self.culture_confucianism
        if self.culture_taoism > 0:
            result[CultureType.TAOISM] = self.culture_taoism
        if self.culture_buddhism > 0:
            result[CultureType.BUDDHISM] = self.culture_buddhism
        return result

    @property
    def total_markers(self) -> int:
        return self.marker_military + self.marker_culture + self.marker_affair + self.marker_power

    def is_playable_by(self, faction: FactionType) -> bool:
        """Check if this card can be played by the given faction."""
        if self.faction_restriction is None:
            return True
        if self.faction_restriction == "jin" and faction == FactionType.JIN:
            return True
        if self.faction_restriction == "north" and faction == FactionType.NORTH:
            return True
        return False

    def __repr__(self) -> str:
        return f"CardDef({self.name}, cost={self.cost}, type={self.card_type.value})"


@dataclass
class Card:
    """A specific card instance in play. Mutable — belongs to a deck/hand/player."""
    definition: CardDef
    owner_player_id: Optional[str] = None  # Which player owns this instance

    # Delegation properties for convenience
    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def cost(self) -> int:
        return self.definition.cost

    @property
    def card_type(self) -> CardType:
        return self.definition.card_type

    @property
    def card_category(self) -> CardCategory:
        return self.definition.card_category

    @property
    def effect_text(self) -> str:
        return self.definition.effect_text

    @property
    def is_friend(self) -> bool:
        return self.definition.is_friend or self.card_type == CardType.FRIEND

    @property
    def is_strategy(self) -> bool:
        return self.card_type == CardType.STRATEGY

    @property
    def is_event(self) -> bool:
        return self.card_type == CardType.EVENT

    @property
    def is_mechanism(self) -> bool:
        return self.card_type == CardType.MECHANISM

    @property
    def is_refugee(self) -> bool:
        return self.card_type == CardType.REFUGEE

    def __repr__(self) -> str:
        owner = f"@{self.owner_player_id}" if self.owner_player_id else ""
        return f"Card({self.name}{owner})"

    def __hash__(self) -> int:
        return id(self)


class CardLibrary:
    """Loads all CardDefs from CSV and provides query methods."""

    def __init__(self, cards: list[CardDef]):
        self._cards: dict[str, CardDef] = {c.card_id: c for c in cards}
        self._by_name: dict[str, list[CardDef]] = {}
        for c in cards:
            self._by_name.setdefault(c.name, []).append(c)

    @property
    def all_cards(self) -> list[CardDef]:
        return list(self._cards.values())

    def get(self, card_id: str) -> Optional[CardDef]:
        return self._cards.get(card_id)

    def get_by_name(self, name: str) -> list[CardDef]:
        """Get all cards with this name (may have multiple copies)."""
        return self._by_name.get(name, [])

    def by_type(self, card_type: CardType) -> list[CardDef]:
        return [c for c in self._cards.values() if c.card_type == card_type]

    def by_category(self, category: CardCategory) -> list[CardDef]:
        return [c for c in self._cards.values() if c.card_category == category]

    def by_faction(self, owner_faction: str) -> list[CardDef]:
        """Filter by owner_faction field (归属)."""
        return [c for c in self._cards.values() if c.owner_faction == owner_faction]

    def by_marker(self, marker: MarkerType) -> list[CardDef]:
        return [c for c in self._cards.values() if c.markers.get(marker, 0) > 0]

    def by_name_exact(self, name: str) -> Optional[CardDef]:
        """Get exactly one card by name. Returns None if not found."""
        cards = self._by_name.get(name, [])
        return cards[0] if cards else None

    def search(self, **kwargs) -> list[CardDef]:
        """Flexible card search by any CardDef field."""
        results = list(self._cards.values())
        for key, value in kwargs.items():
            if key == 'card_type' and not isinstance(value, CardType):
                value = CardType(value)
            if key == 'card_category' and not isinstance(value, CardCategory):
                value = CardCategory(value)
            results = [c for c in results if getattr(c, key, None) == value]
        return results

    def __len__(self) -> int:
        return len(self._cards)

    def __repr__(self) -> str:
        return f"CardLibrary({len(self._cards)} cards)"
