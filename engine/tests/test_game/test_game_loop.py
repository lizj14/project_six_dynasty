"""Integration tests — full game simulation with DummyAI."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestGameEngine:
    """Tests for the complete game loop."""

    @pytest.fixture
    def engine_setup(self):
        """Setup a game engine with 4 DummyAIs."""
        from cards.loader import load_card_design_csv
        from ai.dummy_ai import DummyAI
        from engine.game import GameEngine

        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        lib = load_card_design_csv(csv_path)
        agents = [
            DummyAI(player_id="north", seed=1),
            DummyAI(player_id="jin_1", seed=2),
            DummyAI(player_id="jin_2", seed=3),
            DummyAI(player_id="jin_3", seed=4),
        ]
        engine = GameEngine(library=lib, agents=agents, seed=42)
        return engine

    def test_game_runs_without_crash(self, engine_setup):
        """A full game with 4 DummyAIs should complete without exceptions."""
        engine = engine_setup
        final_state = engine.run()

        assert final_state.phase.value == "game_over"
        assert final_state.round <= 10  # Game ends by round 10 at latest

    def test_game_has_winner(self, engine_setup):
        """After a game, there should be a valid winner."""
        engine = engine_setup
        engine.run()

        scores = engine.get_scores()
        assert len(scores) == 4
        # All scores should be non-negative
        for pid, vp in scores.items():
            assert vp >= 0, f"Player {pid} has negative VP: {vp}"

        winner = engine.get_winner()
        assert winner is not None

    def test_multiple_games_deterministic(self, engine_setup):
        """Same seed should produce same result."""
        from cards.loader import load_card_design_csv
        from ai.dummy_ai import DummyAI
        from engine.game import GameEngine

        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        lib = load_card_design_csv(csv_path)

        # Run two games with same seed
        scores1 = _run_game_with_seed(lib, 42)
        scores2 = _run_game_with_seed(lib, 42)
        assert scores1 == scores2, "Same seed should produce identical results"

    def test_game_ends_by_round_10(self, engine_setup):
        """Game must end by round 10."""
        engine = engine_setup
        final_state = engine.run()
        assert final_state.round <= 10

    def test_ten_games_no_crash(self, engine_setup):
        """Run 10 games with different seeds — all should complete."""
        import random
        from cards.loader import load_card_design_csv
        from ai.dummy_ai import DummyAI
        from engine.game import GameEngine

        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "card_design.csv"
        )
        if not os.path.exists(csv_path):
            pytest.skip("card_design.csv not found")

        lib = load_card_design_csv(csv_path)

        for i in range(10):
            seed = i * 100 + 1
            agents = [
                DummyAI(player_id="north", seed=seed),
                DummyAI(player_id="jin_1", seed=seed + 1),
                DummyAI(player_id="jin_2", seed=seed + 2),
                DummyAI(player_id="jin_3", seed=seed + 3),
            ]
            engine = GameEngine(library=lib, agents=agents, seed=seed)
            try:
                final_state = engine.run()
                assert final_state.phase.value == "game_over"
            except Exception as e:
                pytest.fail(f"Game {i} (seed={seed}) crashed: {e}")


def _run_game_with_seed(lib, seed):
    """Helper: run a game and return scores."""
    from ai.dummy_ai import DummyAI
    from engine.game import GameEngine

    agents = [
        DummyAI(player_id="north", seed=seed),
        DummyAI(player_id="jin_1", seed=seed + 1),
        DummyAI(player_id="jin_2", seed=seed + 2),
        DummyAI(player_id="jin_3", seed=seed + 3),
    ]
    engine = GameEngine(library=lib, agents=agents, seed=seed)
    engine.run()
    return engine.get_scores()
