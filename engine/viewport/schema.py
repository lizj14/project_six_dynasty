"""TypedDict data structures for the viewport system.

These define the shape of data returned by Viewport methods and the
SnapshotViewport's internal dict.  All values are plain Python primitives
— no Card, GameState, or PlayerState references.
"""

from __future__ import annotations

from typing import TypedDict, Optional, Union


# ================================================================
# Card summaries
# ================================================================

class CardSummary(TypedDict, total=False):
    name: str
    card_id: str
    cost: int
    card_type: str
    card_category: str
    effect_text: str
    effect_summary: str
    markers: dict[str, int]        # {"军事": 1, "文化": 0, ...}
    is_friend: bool
    is_strategy: bool
    is_event: bool
    owner_faction: str
    owner_player_id: Optional[str]
    history_vp: int
    resource_option_army: int
    resource_option_vp: int
    culture_tags: dict[str, int]


# ================================================================
# Location summaries
# ================================================================

class LocationSummary(TypedDict):
    controller: str                # "north", "jin_p1", "sima", "neutral", "empty"
    is_fortified: bool
    culture_marker: Optional[str]  # "confucianism", "taoism", "buddhism", or None
    culture_locked: bool


class RegionSummary(TypedDict):
    name: str
    control_marker: Optional[str]  # which player's marker, or None
    locations: list[str]           # location IDs in this region


# ================================================================
# Player summaries
# ================================================================

class PublicPlayerSummary(TypedDict, total=False):
    player_id: str
    faction: str
    hero: Optional[CardSummary]
    staff_count: int
    staff_names: list[str]
    history_count: int
    history_names: list[str]
    military: int
    vp: int
    army_placed_count: int
    army_reserve_count: int
    army_reserve_revealed_vp: int
    army_reserve_revealed_military: int
    hand_count: int
    marker_military: int
    marker_culture: int
    marker_affair: int
    marker_power: int
    has_expedition_marker: bool
    game_end_marker: bool
    start_order: int
    culture_contributions: dict[str, int]
    # Jin-specific:
    prestige: int
    contribution: int
    order: int
    order_seq: int


class PrivatePlayerSummary(TypedDict, total=False):
    hand: list[CardSummary]
    staff: list[CardSummary]
    history: list[CardSummary]
    hero: Optional[CardSummary]
    can_take_hand_action: bool
    can_take_court_action: bool
    extra_hand_actions: int
    extra_court_actions: int
    extra_hand_action_filter: Optional[str]
    has_drawn_quick: bool
    has_fortified_quick: bool
    has_taken_hand_action: bool
    has_taken_court_action: bool
    hand_action_taken_count: int
    court_action_taken_count: int
    activated_card_ids: list[str]
    staff_free_slots: int
    staff_limit: int
    hand_limit: int


# ================================================================
# Track summaries
# ================================================================

class VPTrack(TypedDict, total=False):
    """player_id → VP, including "sima"."""
    north: int
    jin_1: int
    jin_2: int
    jin_3: int
    sima: int


class CultureTrackLevel(TypedDict):
    level: int
    supply: int


class CultureTracks(TypedDict):
    confucianism: dict  # CultureTrackLevel
    taoism: dict
    buddhism: dict


class PrestigeTrack(TypedDict):
    jin_1: int
    jin_2: int
    jin_3: int
    sima: int


class ContributionTrack(TypedDict):
    jin_1: int
    jin_2: int
    jin_3: int


class OrderTrack(TypedDict):
    jin_1: int
    jin_2: int
    jin_3: int


# ================================================================
# Deck / court summaries
# ================================================================

class DeckInfo(TypedDict):
    deck_count: int                # Cards remaining in deck (hidden)
    discard: list[str]             # Discard pile card names (face-up, public)


class CourtInfo(TypedDict):
    cards: list[CardSummary]       # Court cards (face-up, public)
    played_this_round: list[CardSummary]


# ================================================================
# Emperor / Sima summaries
# ================================================================

class EmperorSummary(TypedDict):
    age: int
    emperor_name: str
    prestige: int
    tasks: list[str]


class SimaSummary(TypedDict):
    military: int
    vp: int
    prestige: int
    army_placed_count: int
    army_reserve_count: int


# ================================================================
# Available actions
# ================================================================

class ActionSummary(TypedDict, total=False):
    action_type: str
    description: str
    target: str
    cost: str
    card_index: int
    card_name: str
    card_id: str
    card_cost: int
    payment_indices: list[int]
    effect_summary: str
    block_costs: str
    block_index: int
    choice_index: int
    source: str


class AvailableActions(TypedDict):
    quick_actions: list[ActionSummary]
    hand_actions: list[ActionSummary]
    court_actions: list[ActionSummary]
    public_actions: list[ActionSummary]
    activate_actions: list[ActionSummary]
    other_actions: list[ActionSummary]


# ================================================================
# Top-level Viewport data (SnapshotViewport internal structure)
# ================================================================

class PublicInfo(TypedDict):
    map: "MapInfo"
    players: dict[str, PublicPlayerSummary]
    court: dict[str, list[CardSummary]]        # "north" | "jin" → cards
    played_this_round: dict[str, list[CardSummary]]
    public_actions: list[CardSummary]
    tracks: "TracksInfo"
    decks: dict[str, DeckInfo]                  # "main" | "north" | "jin"
    forced_event_pile_count: int
    refugee_supply_count: int
    emperor: EmperorSummary
    sima: SimaSummary
    expedition_marker_location: Optional[str]


class MapInfo(TypedDict):
    locations: dict[str, LocationSummary]
    regions: dict[str, RegionSummary]


class TracksInfo(TypedDict):
    vp: dict[str, int]
    culture: dict[str, dict]
    prestige: dict[str, int]
    contribution: dict[str, int]
    order: dict[str, int]


class PrivateInfo(TypedDict):
    hand: list[CardSummary]
    staff: list[CardSummary]
    history: list[CardSummary]
    hero: Optional[CardSummary]
    secret_goal: Optional[CardSummary]
    can_take_hand_action: bool
    can_take_court_action: bool
    extra_hand_actions: int
    extra_court_actions: int
    extra_hand_action_filter: Optional[str]
    has_drawn_quick: bool
    has_fortified_quick: bool
    has_taken_hand_action: bool
    has_taken_court_action: bool
    hand_action_taken_count: int
    court_action_taken_count: int
    activated_card_ids: list[str]
    staff_free_slots: int
    staff_limit: int
    hand_limit: int


class ViewportData(TypedDict):
    viewer_id: str
    mode: str
    round: int
    phase: str
    turn_order: list[str]
    active_player_index: int
    game_end_marker: Optional[str]
    game_end_reason: Optional[str]
    public: PublicInfo
    private: PrivateInfo
    available_actions: AvailableActions
