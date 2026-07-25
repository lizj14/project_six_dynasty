"""测试游戏阶段管理 — setup_game, preparation, settlement."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from models.enums import FactionType, CardType, PhaseType, ControlState
from models.card import CardDef, Card, CardLibrary
from models.player import PlayerState
from models.game_state import GameState


class TestSetupGame:
    def test_setup_creates_all_players(self):
        """setup_game creates north + 3 Jin + sima + emperor."""
        from engine.phases import setup_game
        from models.enums import ControlState
        lib = CardLibrary([])
        from ai.dummy_ai import DummyAI
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        state = setup_game(lib, agents, seed=42)
        assert state.north_player is not None
        assert len(state.jin_players) == 3
        assert state.sima is not None
        assert state.emperor is not None
        # Jin players have orders 0, 1, 2
        assert [p.order for p in state.jin_players] == [0, 1, 2]

    def test_preset_hands_guarantees_cards_in_hand(self):
        """preset_hands ensures specified cards are in the player's hand."""
        from engine.phases import setup_game
        from config.version import Version
        v = Version.load("v1.0")
        from ai.dummy_ai import DummyAI
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        # Find two non-hero, non-goal cards for testing
        eligible = [c for c in v.card_library.all_cards
                    if c.card_type.value not in ("hero", "goal", "emperor",
                        "refugee", "initial", "public")
                    and c.owner_faction != "初始"]
        assert len(eligible) >= 2, "Need at least 2 eligible cards for test"
        card1, card2 = eligible[0].name, eligible[1].name

        state = setup_game(
            v.card_library, agents, seed=42,
            version=v,
            preset_hands={"jin_1": [card1, card2]},
        )
        jin1 = state.jin_players[0]
        jin1_hand = [c.name for c in jin1.hand]
        assert card1 in jin1_hand, f"{card1!r} should be in jin_1 hand"
        assert card2 in jin1_hand, f"{card2!r} should be in jin_1 hand"

    def test_preset_hands_missing_card_raises(self):
        """preset_hands with a non-existent card name raises ValueError."""
        from engine.phases import setup_game
        from config.version import Version
        v = Version.load("v1.0")
        from ai.dummy_ai import DummyAI
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        with pytest.raises(ValueError, match="preset_hands"):
            setup_game(
                v.card_library, agents, seed=99,
                version=v,
                preset_hands={"jin_1": ["__NONEXISTENT_CARD__"]},
            )


class TestPreparationPhase:
    def test_runs_without_crash(self):
        """run_preparation_phase should execute without error."""
        from engine.phases import run_preparation_phase
        import random
        lib = CardLibrary([])
        from ai.dummy_ai import DummyAI
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        state = GameState(
            round=1, phase=PhaseType.PREPARATION,
            north_player=PlayerState("north", faction=FactionType.NORTH),
            jin_players=[
                PlayerState("jin_1", faction=FactionType.JIN, order=0),
                PlayerState("jin_2", faction=FactionType.JIN, order=1),
                PlayerState("jin_3", faction=FactionType.JIN, order=2),
            ],
            locations={}, map_adjacencies=[],
            turn_order=["north", "jin_1", "jin_2", "jin_3"],
            active_player_index=0, seed=42,
        )
        rng = random.Random(42)
        run_preparation_phase(state, rng)
        # After preparation, phase should be ACTION
        assert state.phase == PhaseType.ACTION


class TestSettlementPhase:
    def test_runs_without_crash(self):
        """run_settlement_phase should execute without error."""
        from engine.phases import run_settlement_phase
        import random
        lib = CardLibrary([])
        from ai.dummy_ai import DummyAI
        agents = [
            DummyAI("north", 1),
            DummyAI("jin_1", 2),
            DummyAI("jin_2", 3),
            DummyAI("jin_3", 4),
        ]
        state = GameState(
            round=1, phase=PhaseType.SETTLEMENT,
            north_player=PlayerState("north", faction=FactionType.NORTH),
            jin_players=[
                PlayerState("jin_1", faction=FactionType.JIN, order=0),
                PlayerState("jin_2", faction=FactionType.JIN, order=1),
                PlayerState("jin_3", faction=FactionType.JIN, order=2),
            ],
            locations={}, map_adjacencies=[],
            turn_order=["north", "jin_1", "jin_2", "jin_3"],
            active_player_index=0, seed=42,
        )
        rng = random.Random(42)
        run_settlement_phase(state, rng)
        # After settlement, round should advance and phase go to PREPARATION
        assert state.round >= 2 or state.phase in (PhaseType.PREPARATION, PhaseType.GAME_OVER)
