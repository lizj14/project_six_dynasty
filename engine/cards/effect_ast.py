"""Effect AST node definitions — the parsed representation of card effects.

Each card's effect_text is parsed into a CardEffect containing one or more
AbilityBlocks. Each AbilityBlock contains a list of EffectSteps.
"""

from dataclasses import dataclass, field
from typing import Optional, Any


# ============================================================
# AST Node Types
# ============================================================

@dataclass
class EffectStep:
    """A single atomic effect step, e.g. '获得3军力' or '摸1张牌'."""
    effect_type: str = ""           # e.g. "gain_military", "gain_vp", "march", etc.
    params: dict[str, Any] = field(default_factory=dict)
    condition: Optional["Condition"] = None  # Optional prerequisite
    source_text: str = ""           # Original text for debugging


@dataclass
class Condition:
    """A condition that must be met for an effect to apply."""
    condition_type: str = ""        # e.g. "control_region", "has_marker", "compare"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Cost:
    """A cost that must be paid for an effect block to execute."""
    cost_type: str = ""             # "discard_cards", "pay_military", "pay_vp"
    params: dict[str, Any] = field(default_factory=dict)  # {"count": N, ...}


@dataclass
class AbilityBlock:
    """A block of effects with a specific timing/trigger.

    Examples:
      - 主动：获得3军力  (ActiveAbility with one step)
      - 被动：每次进军后，获得1vp  (PassiveAbility with trigger)
      - 登场：转化[长安][弘农]  (EnterPlay with two convert steps)
      - 强制：选择1个...  (ForcedEffect)
      - 行动：3军力  (StrategyAction for court cards)
    """
    ability_type: str = ""          # "active", "passive", "enter", "forced", "strategy_action"
    trigger: Optional[str] = None   # For passives: "on_march", "on_archive", etc.
    trigger_scope: str = "self"     # "self" (owner only) or "any" (any player)
    trigger_filter: Optional[dict] = None  # e.g. {"marker": "power"}
    condition: Optional["Condition"] = None  # Block-level condition (e.g. 袁乔: hand_count==0)
    costs: list["Cost"] = field(default_factory=list)  # Block-level costs
    steps: list[EffectStep] = field(default_factory=list)
    usurp_steps: list[EffectStep] = field(default_factory=list)  # 僭越 extra effects
    choice_options: list[list[EffectStep]] = field(default_factory=list)  # For 选择1项
    resource_option: Optional[dict] = None  # For strategy cards: {"army": 1, "vp": 0}
    modifier: Optional[dict] = None  # e.g. {"usurp_with_tie": true}
    source_text: str = ""


@dataclass
class CardEffect:
    """Complete parsed effect for a card. Contains all ability blocks."""
    card_name: str = ""
    raw_text: str = ""
    blocks: list[AbilityBlock] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # culture, military, power, affair
    is_usurp: bool = False
    faction_restriction: Optional[str] = None
    play_condition: Optional[Condition] = None  # e.g. "控制[巴蜀]"
    restrictions: list[str] = field(default_factory=list)
    # e.g. "cannot_be_archived", "cannot_be_drafted", "cannot_be_discarded"


# ============================================================
# Effect Type Constants
# ============================================================

class EffectType:
    """Constants for effect_type values."""
    # Resource changes
    GAIN_MILITARY = "gain_military"
    GAIN_VP = "gain_vp"
    LOSE_VP = "lose_vp"
    LOSE_MILITARY = "lose_military"
    PAY_MILITARY = "pay_military"
    PAY_VP = "pay_vp"

    # Card operations
    DRAW_CARDS = "draw_cards"
    DISCARD_CARDS = "discard_cards"
    ARCHIVE_THIS = "archive_this"
    ARCHIVE_CARD = "archive_card"
    ARCHIVE_COURT = "archive_court"
    SEARCH = "search"
    DRAFT = "draft"            # 征发
    SUPPLY_COURT = "supply_court"  # 补充牌到朝堂区
    PLAY_CARD = "play_card"

    # Map actions
    MARCH = "march"
    OCCUPY = "occupy"
    CONVERT = "convert"
    FORTIFY = "fortify"
    SPREAD_CULTURE = "spread_culture"

    # Tracks
    RAISE_ORDER = "raise_order"
    LOWER_ORDER = "lower_order"
    RAISE_PRESTIGE = "raise_prestige"
    LOWER_PRESTIGE = "lower_prestige"
    RAISE_CONTRIBUTION = "raise_contribution"
    LOWER_CONTRIBUTION = "lower_contribution"

    # Culture
    RAISE_CULTURE_LEVEL = "raise_culture_level"

    # Markers / Tokens
    GET_EXPEDITION = "get_expedition"
    ADD_REFUGEE = "add_refugee"
    PLACE_ARMY = "place_army"
    REMOVE_ARMY = "remove_army"
    REMOVE_FROM_GAME = "remove_from_game"

    # Choices
    CHOOSE = "choose"
    CONDITIONAL = "conditional"

    # Meta
    NOOP = "noop"
    RAW = "raw"  # Unparsed effect, stored as text

    # Meta-effects
    EXTRA_ACTION = "extra_action"
    TARGETED_EFFECT = "targeted_effect"
    RESHUFFLE_EMPEROR = "reshuffle_emperor"  # 重洗君主牌堆

    # Map actions (variants)
    CONVERT_OWN_TO_NEUTRAL = "convert_own_to_neutral"
    CONVERT_TO_NEUTRAL = "convert_to_neutral"
    CONVERT_TO_SIMA = "convert_to_sima"


class AbilityType:
    """Constants for ability_type values."""
    ACTIVE = "active"
    PASSIVE = "passive"
    ENTER = "enter"
    FORCED = "forced"
    STRATEGY_ACTION = "strategy_action"
    STRATEGY_PASSIVE = "strategy_passive"
    RESOURCE_OPTION = "resource_option"
    USURP = "usurp"


class TriggerType:
    """Constants for trigger values on passive abilities."""
    ON_MARCH = "on_march"
    ON_OCCUPY = "on_occupy"
    ON_CONVERT = "on_convert"
    ON_ARCHIVE = "on_archive"
    ON_DISCARD = "on_discard"
    ON_FORTIFY = "on_fortify"
    ON_SPREAD_CULTURE = "on_spread_culture"
    ON_PLAY_CARD = "on_play_card"
    ON_GAIN_VP = "on_gain_vp"
    ON_GAIN_CONTRIBUTION = "on_gain_contribution"
    ON_GAIN_PRESTIGE = "on_gain_prestige"
    ON_ORDER_CHANGE = "on_order_change"
    ON_TURN_START = "on_turn_start"
    ON_TURN_END = "on_turn_end"
    ON_USURP = "on_usurp"
    ON_COURT_ACTION = "on_court_action"
    ON_CARD_LEAVE = "on_card_leave"
    ON_CARD_ENTER = "on_card_enter"
    ON_REGION_REWARD = "on_region_reward"
    ALWAYS = "always"
