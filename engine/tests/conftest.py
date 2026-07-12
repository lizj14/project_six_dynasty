"""Shared test fixtures for the game engine."""

import os
import sys
import pytest

# Add the engine directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.enums import (
    FactionType, CardType, PhaseType, CultureType, Region,
    MarkerType, TerrainType, ControlState,
)
from models.card import CardDef, Card, CardLibrary
from models.player import PlayerState
from models.location import LocationState, RegionState, LocationDef, AdjacencyDef
from models.game_state import GameState, SimaState, EmperorState, CultureTrackState


# === Card fixtures ===

@pytest.fixture
def sample_card_def():
    """A simple 士卒 card definition."""
    return CardDef(
        card_id="initial_士兵_1",
        name="士兵",
        owner_faction="初始",
        cost=0,
        card_type=CardType.STRATEGY,
        card_category=CardType.STRATEGY,  # will use INITIAL
        effect_text="行动：3军力",
        resource_military=1,
        resource_vp=0,
        history_vp=1,
        marker_military=1,
    )


@pytest.fixture
def sample_card(sample_card_def):
    """A Card instance wrapping the sample card def."""
    return Card(definition=sample_card_def, owner_player_id="north")


@pytest.fixture
def sample_refugee_def():
    """A 流民 card definition."""
    return CardDef(
        card_id="initial_流民_1",
        name="流民",
        owner_faction="初始",
        cost=0,
        card_type=CardType.STRATEGY,
        card_category=CardType.STRATEGY,
        effect_text="被动：[流民]被存档时，自动放置回供应堆。存档[流民]的玩家获得2vp。",
        resource_military=0,
        resource_vp=0,
        history_vp=0,
    )


# === Player fixtures ===

@pytest.fixture
def north_player():
    """A basic North player."""
    return PlayerState(
        player_id="north",
        faction=FactionType.NORTH,
        military=5,
        vp=0,
        prestige=0,
        contribution=0,
        army_reserve_count=10,
    )


@pytest.fixture
def jin_player_1():
    """A basic Jin player 1."""
    return PlayerState(
        player_id="jin_1",
        faction=FactionType.JIN,
        military=1,
        vp=0,
        prestige=0,
        contribution=0,
        order=0,
        army_reserve_count=8,
    )


@pytest.fixture
def jin_player_2():
    """A basic Jin player 2."""
    return PlayerState(
        player_id="jin_2",
        faction=FactionType.JIN,
        military=1,
        vp=0,
        prestige=0,
        contribution=0,
        order=1,
        army_reserve_count=8,
    )


@pytest.fixture
def jin_player_3():
    """A basic Jin player 3."""
    return PlayerState(
        player_id="jin_3",
        faction=FactionType.JIN,
        military=1,
        vp=0,
        prestige=0,
        contribution=0,
        order=2,
        army_reserve_count=8,
    )


# === Location fixtures ===

@pytest.fixture
def sample_locations():
    """A minimal set of locations for testing."""
    return {
        "长安": LocationState(location_id="长安", controller=ControlState.NORTH),
        "弘农": LocationState(location_id="弘农", controller=ControlState.NEUTRAL),
        "洛阳": LocationState(location_id="洛阳", controller=ControlState.SIMA),
        "安定": LocationState(location_id="安定", controller=ControlState.NEUTRAL),
        "天水": LocationState(location_id="天水", controller=ControlState.NEUTRAL),
    }


@pytest.fixture
def sample_adjacencies():
    """Minimal adjacency data for testing."""
    return [
        AdjacencyDef("长安", "弘农", TerrainType.DIFFICULT),
        AdjacencyDef("长安", "安定", TerrainType.SIMPLE),
        AdjacencyDef("长安", "天水", TerrainType.SIMPLE),
        AdjacencyDef("弘农", "洛阳", TerrainType.SIMPLE),
    ]


# === GameState fixture ===

@pytest.fixture
def minimal_state(north_player, jin_player_1, jin_player_2, jin_player_3,
                   sample_locations, sample_adjacencies):
    """A minimal working GameState for testing."""
    # Set up control states that match player IDs
    state = GameState(
        round=1,
        phase=PhaseType.ACTION,
        north_player=north_player,
        jin_players=[jin_player_1, jin_player_2, jin_player_3],
        locations=sample_locations,
        map_adjacencies=sample_adjacencies,
        turn_order=["north", "jin_1", "jin_2", "jin_3"],
        active_player_index=0,
        seed=42,
    )
    return state


# === CardLibrary fixture ===

@pytest.fixture
def card_library():
    """Load the actual card library from Version.load('v1.0') (cards_compiled.json).

    Falls back to card_design.csv if v1.0 version is not available.
    """
    try:
        from config.version import Version
        v = Version.load('v1.0')
        return v.card_library
    except Exception:
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "card_design.csv"
        )
        if os.path.exists(csv_path):
            from cards.loader import load_card_design_csv
            return load_card_design_csv(csv_path)
        return CardLibrary([])
