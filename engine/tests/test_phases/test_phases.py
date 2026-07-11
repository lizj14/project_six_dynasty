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
