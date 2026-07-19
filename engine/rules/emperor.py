"""Emperor system — dice, tasks, age track. Rulebook §3.5, §4.2."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
from dataclasses import dataclass, field
from typing import Optional

from models.enums import EmperorTaskType


# Emperor dice faces: 1-6
# Cards define which faces map to which tasks
# Default mapping (will be overridden by emperor card data):
DEFAULT_DICE_FACES = {
    1: EmperorTaskType.EXPANSION,
    2: EmperorTaskType.EXPANSION,
    3: EmperorTaskType.FORTIFY,
    4: EmperorTaskType.CULTURE,
    5: EmperorTaskType.REFORM,
    6: EmperorTaskType.ART,  # Art = auto 2vp for Sima
}

# Task descriptions for AI
TASK_REQUIREMENTS = {
    EmperorTaskType.EXPANSION: {
        "label": "扩张",
        "description": "在指定区域执行进军或转化，且必须放置司马家部队",
    },
    EmperorTaskType.FORTIFY: {
        "label": "加固",
        "description": "执行一次加固行动，目标必须是司马家部队所在地点",
    },
    EmperorTaskType.CULTURE: {
        "label": "文化",
        "description": "打出一张[文化]标记的牌，或执行一张[文化]标记候选策略牌",
    },
    EmperorTaskType.REFORM: {
        "label": "改革",
        "description": "进行一次策略牌的手牌行动，或进行一次存档行动",
    },
    EmperorTaskType.ART: {
        "label": "艺术",
        "description": "自动触发：司马家直接获得2vp",
    },
}


@dataclass
class EmperorTask:
    """A single active task from an emperor die."""
    task_type: EmperorTaskType
    completed: bool = False
    completed_by: Optional[str] = None  # player_id


@dataclass
class EmperorState:
    """Runtime emperor state (moved from game_state.py for clarity)."""
    current_emperor: Optional["CardDef"] = None
    emperor_deck: list = field(default_factory=list)
    age: int = 1                       # Current position on age track
    active_tasks: list[EmperorTask] = field(default_factory=list)


def roll_emperor_dice(state: "GameState", rng: random.Random) -> list[dict]:
    """Roll emperor dice during preparation phase.

    Returns list of events. Mutates state.emperor.active_tasks.

    Rule:每有3点司马家军力，投掷1个骰子（最多5个）。
      艺术面 → 司马家+2vp，移走骰子
      其他面 → 放置到君主牌上作为任务标记
    """
    dice_count = min(5, state.sima.military // 3)
    events = []

    # Clear tasks from previous round (tasks are per-round only)
    state.emperor.active_tasks = []

    for _ in range(dice_count):
        roll = rng.randint(1, 6)
        # Get task type from emperor card, or use default
        if state.emperor.current_emperor:
            dice_faces = getattr(state.emperor.current_emperor, 'emperor_tasks', None)
            if dice_faces and roll <= len(dice_faces):
                task_type_str = dice_faces[roll - 1]
                # Map Chinese task name to enum
                task_type = _parse_task_type(task_type_str)
            else:
                task_type = DEFAULT_DICE_FACES.get(roll, EmperorTaskType.ART)
        else:
            task_type = DEFAULT_DICE_FACES.get(roll, EmperorTaskType.ART)

        if task_type == EmperorTaskType.ART:
            state.sima.vp += 2
            events.append({"type": "emperor_dice", "roll": roll, "result": "art",
                           "sima_vp": 2})
        else:
            task = EmperorTask(task_type=task_type)
            state.emperor.active_tasks.append(task)
            events.append({"type": "emperor_dice", "roll": roll,
                           "result": "task", "task": task_type.value})

    return events


def check_task_completion(state: "GameState", player_id: str,
                          action_type: str, context: dict = None) -> list[dict]:
    """Check if a player's action completes any active emperor tasks.

    Called after each player action. Returns events with any rewards.

    action_type: "march", "convert", "fortify", "play_card", "court_action", "archive"
    context: additional info like card markers, location, etc.
    """
    events = []
    any_newly_completed = False
    player = state.get_player(player_id)
    if not player or player.faction.value != "jin":
        return events

    from models.enums import FactionType
    if player.faction != FactionType.JIN:
        return events

    for task in state.emperor.active_tasks:
        if task.completed:
            continue

        completed = False

        if task.task_type == EmperorTaskType.EXPANSION:
            if action_type in ("march", "convert"):
                # Must have placed a Sima army
                if context and context.get("used_sima_army"):
                    completed = True

        elif task.task_type == EmperorTaskType.FORTIFY:
            if action_type == "fortify":
                # Must target a Sima location
                if context and context.get("target_is_sima"):
                    completed = True

        elif task.task_type == EmperorTaskType.CULTURE:
            if action_type == "play_card":
                if context and context.get("has_culture_marker"):
                    completed = True
            elif action_type == "court_action":
                if context and context.get("has_culture_marker"):
                    completed = True

        elif task.task_type == EmperorTaskType.REFORM:
            if action_type == "play_card":
                if context and context.get("is_strategy"):
                    completed = True
            elif action_type == "archive":
                completed = True

        if completed:
            task.completed = True
            task.completed_by = player_id
            player.vp += 2
            any_newly_completed = True
            events.append({"type": "emperor_task_completed",
                           "player": player_id,
                           "task": task.task_type.value,
                           "vp_reward": 2})

    # Check if ALL active tasks are now complete → Sima prestige +1
    # Only fire if at least one task was newly completed in this call
    if any_newly_completed and state.emperor.active_tasks and all(
        t.completed for t in state.emperor.active_tasks
    ):
        state.sima.prestige = min(9, state.sima.prestige + 1)
        events.append({"type": "emperor_all_tasks_complete",
                       "sima_prestige": state.sima.prestige})

    return events


def check_emperor_age(state: "GameState", rng: random.Random) -> list[dict]:
    """Check emperor age during settlement phase.

    Returns events. Rule: roll 1d6, if > age → age+1 & prestige+1,
    otherwise emperor dies → reset age, reshuffle emperor deck.
    """
    events = []
    if not state.emperor.current_emperor:
        return events

    roll = rng.randint(1, 6)
    if roll > state.emperor.age:
        state.emperor.age += 1
        # Prestige no longer grows from emperor age — only from all-tasks completion
        events.append({"type": "emperor_age", "roll": roll, "age": state.emperor.age,
                       "result": "aged"})
    else:
        # Emperor dies
        old_age = state.emperor.age
        state.emperor.age = 1
        state.emperor.active_tasks = []
        if state.emperor.emperor_deck:
            rng.shuffle(state.emperor.emperor_deck)
            state.emperor.current_emperor = state.emperor.emperor_deck[0]
            state.sima.prestige = state.emperor.current_emperor.initial_prestige
        events.append({"type": "emperor_death", "roll": roll, "old_age": old_age,
                       "new_emperor": getattr(state.emperor.current_emperor, 'name', '?'),
                       "sima_prestige": state.sima.prestige})

    return events


def _parse_task_type(name: str) -> EmperorTaskType:
    """Parse a Chinese task name to EmperorTaskType enum."""
    name = name.strip()
    if "扩张" in name:
        return EmperorTaskType.EXPANSION
    if "加固" in name:
        return EmperorTaskType.FORTIFY
    if "文化" in name:
        return EmperorTaskType.CULTURE
    if "改革" in name:
        return EmperorTaskType.REFORM
    if "艺术" in name:
        return EmperorTaskType.ART
    return EmperorTaskType.ART
