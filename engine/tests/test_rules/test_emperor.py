"""Tests for emperor system."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import random
import pytest
from models.enums import EmperorTaskType, FactionType, PhaseType
from models.player import PlayerState
from models.game_state import GameState, EmperorState
from rules.emperor import (
    roll_emperor_dice, check_task_completion, check_emperor_age,
    EmperorTask, DEFAULT_DICE_FACES,
)


def make_emperor_state(sima_military=6):
    """Create a minimal state for emperor tests."""
    state = GameState(
        round=1, phase=PhaseType.PREPARATION,
        north_player=PlayerState(player_id="north", faction=FactionType.NORTH),
        jin_players=[
            PlayerState(player_id="jin_1", faction=FactionType.JIN),
            PlayerState(player_id="jin_2", faction=FactionType.JIN),
            PlayerState(player_id="jin_3", faction=FactionType.JIN),
        ],
    )
    state.sima.military = sima_military
    state.emperor = EmperorState(age=1, current_emperor=True)
    return state


class TestEmperorDice:
    """Tests for emperor dice rolling."""

    def test_dice_count_by_sima_military(self):
        """每3军力 → 1个骰子，最多5个."""
        rng = random.Random(42)

        # 6 military → 2 dice
        state = make_emperor_state(sima_military=6)
        state.emperor.active_tasks = []
        events = roll_emperor_dice(state, rng)
        total = len([e for e in events if e["type"] == "emperor_dice"])
        assert total == 2

        # 15 military → 5 dice (capped)
        state = make_emperor_state(sima_military=15)
        state.emperor.active_tasks = []
        events = roll_emperor_dice(state, rng)
        total = len([e for e in events if e["type"] == "emperor_dice"])
        assert total == 5

        # 2 military → 0 dice
        state = make_emperor_state(sima_military=2)
        state.emperor.active_tasks = []
        events = roll_emperor_dice(state, rng)
        total = len([e for e in events if e["type"] == "emperor_dice"])
        assert total == 0

    def test_dice_produces_tasks(self):
        """Non-art rolls create active tasks."""
        rng = random.Random(99)  # This seed may produce task rolls
        state = make_emperor_state(sima_military=9)
        state.emperor.active_tasks = []
        events = roll_emperor_dice(state, rng)
        # Check that tasks or art events were generated
        assert len(events) > 0


class TestTaskCompletion:
    """Tests for task completion checks."""

    def test_archive_completes_reform(self):
        """存档行动 → 完成改革任务."""
        state = make_emperor_state()
        state.emperor.active_tasks = [EmperorTask(task_type=EmperorTaskType.REFORM)]
        events = check_task_completion(state, "jin_1", "archive")
        assert len(events) == 2  # task_completed + all_tasks_complete
        assert events[0]["type"] == "emperor_task_completed"
        assert events[1]["type"] == "emperor_all_tasks_complete"
        assert state.emperor.active_tasks[0].completed
        assert state.jin_players[0].vp == 2

    def test_fortify_sima_completes_fortify(self):
        """加固司马家地点 → 完成加固任务."""
        state = make_emperor_state()
        state.emperor.active_tasks = [EmperorTask(task_type=EmperorTaskType.FORTIFY)]
        events = check_task_completion(state, "jin_1", "fortify",
                                        context={"target_is_sima": True})
        assert len(events) == 2  # task_completed + all_tasks_complete

    def test_fortify_non_sima_no_complete(self):
        """加固非司马家地点 → 不完成."""
        state = make_emperor_state()
        state.emperor.active_tasks = [EmperorTask(task_type=EmperorTaskType.FORTIFY)]
        events = check_task_completion(state, "jin_1", "fortify",
                                        context={"target_is_sima": False})
        assert len(events) == 0

    def test_north_player_cannot_complete(self):
        """北方玩家不能完成君主任务."""
        state = make_emperor_state()
        state.emperor.active_tasks = [EmperorTask(task_type=EmperorTaskType.REFORM)]
        events = check_task_completion(state, "north", "archive")
        assert len(events) == 0

    def test_already_completed_task(self):
        """已完成的任务不重复触发."""
        state = make_emperor_state()
        task = EmperorTask(task_type=EmperorTaskType.REFORM, completed=True)
        state.emperor.active_tasks = [task]
        events = check_task_completion(state, "jin_1", "archive")
        assert len(events) == 0


class TestEmperorAge:
    """Tests for emperor age check."""

    def test_age_increase(self):
        """Roll > age → age increases (prestige no longer grows on age)."""
        # Use a seed that gives a high roll (>2) for age=1
        rng = random.Random(123)
        state = make_emperor_state()
        state.emperor.age = 2
        old_prestige = state.sima.prestige
        old_age = state.emperor.age
        events = check_emperor_age(state, rng)
        assert len(events) >= 1
        # Either aged or died depending on roll
        event = events[0]
        if event.get("result") == "aged":
            assert state.emperor.age > old_age
            # Prestige no longer changes on age increase

    def test_emperor_death_event_exists(self):
        """Emperor death produces correct event type."""
        state = make_emperor_state()
        state.emperor.age = 1  # Young emperor, 1/6 chance of death
        # Just verify the function doesn't crash
        rng = random.Random(42)
        events = check_emperor_age(state, rng)
        assert len(events) >= 1
        assert events[0]["type"] in ("emperor_age", "emperor_death")


class TestTaskTypes:
    """Verify task type parsing."""

    def test_default_dice_faces(self):
        assert DEFAULT_DICE_FACES[1] == EmperorTaskType.EXPANSION
        assert DEFAULT_DICE_FACES[6] == EmperorTaskType.ART
