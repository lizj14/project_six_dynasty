"""Base action types and action result."""

from dataclasses import dataclass, field
from typing import Optional, Any
from abc import ABC, abstractmethod


@dataclass
class ActionResult:
    """Result of executing an action. Contains events and the modified state."""
    success: bool
    events: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    # Modified state (the engine will apply these changes)
    state_changes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, events: list[dict] = None) -> "ActionResult":
        return cls(success=True, events=events or [])

    @classmethod
    def fail(cls, error: str) -> "ActionResult":
        return cls(success=False, error=error)


class GameAction(ABC):
    """Abstract base class for all game actions."""

    action_type: str = "base"
    player_id: str = ""

    @abstractmethod
    def validate(self, state: "GameState") -> ActionResult:
        """Check if this action is legal given the current game state."""
        ...

    @abstractmethod
    def execute(self, state: "GameState") -> ActionResult:
        """Execute this action, mutating the game state."""
        ...

    @abstractmethod
    def cost_description(self, state: "GameState") -> str:
        """Human-readable description of the cost."""
        ...
