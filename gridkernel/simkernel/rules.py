"""The interface a game must implement. Replace this to replace the game."""
from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any
from .commands import Command
class Rules[S](ABC):
    """Pure simulation rules.
    Contract:
      * step() must be a pure, deterministic function of (state, tick, commands).
        No clocks, no unseeded randomness, no dependence on dict/set iteration
        order for anything that affects results.
      * step() must NOT mutate `state`. It may return `state` itself if nothing
        changed. The kernel stores states by reference in snapshots.
      * `commands` is the tick's commands, ascending by command ID.
      * step() is called for every tick, even ticks without commands.
    """
    #: Identifies the ruleset and its encoding version; mixed into every hash.
    name: str
    @abstractmethod
    def initial_state(self) -> S:
        """The world before tick 0."""
    @abstractmethod
    def validate_action(self, action: object) -> None:
        """Raise InvalidCommandError if `action` is malformed."""
    @abstractmethod
    def step(self, state: S, tick: int, commands: Sequence[Command]) -> S:
        """Return the world after `tick`."""
    @abstractmethod
    def encode_state(self, state: S) -> bytes:
        """Canonical byte encoding: equal worlds <=> equal bytes."""
    @abstractmethod
    def export_state(self, state: S) -> Any:
        """An independent copy that callers may keep or mutate without
        affecting the engine."""
