"""Public facade tying together command store, rules and history."""
from __future__ import annotations
from collections.abc import Iterable
from typing import Any
from .commands import Command, require_int, require_text
from .errors import ConfigurationError, InvalidCommandError, TickError
from .history import INITIAL_TICK, History
from .rules import Rules
from .store import CommandStore
class Engine[S]:
    def __init__(
        self,
        rules: Rules[S],
        *,
        snapshot_interval: int = 64,
        query_cache_size: int = 16,
    ) -> None:
        if not isinstance(rules, Rules):
            raise ConfigurationError("rules must be an instance of simkernel.Rules")
        self._rules = rules
        self._store = CommandStore()
        self._history: History[S] = History(
            rules,
            self._store,
            snapshot_interval=snapshot_interval,
            query_cache_size=query_cache_size,
        )
    # -- commands ----------------------------------------------------------
    def _validate(self, command: object) -> None:
        if type(command) is not Command:
            raise InvalidCommandError(f"expected a Command, got {type(command).__name__}")
        require_text(command.command_id, "command_id")
        require_int(command.tick, "tick", minimum=0)
        self._rules.validate_action(command.action)
    def submit(self, command: Command) -> bool:
        """Submit one command. Returns True if it was new, False if it was an
        identical duplicate (a no-op). Raises InvalidCommandError for malformed
        commands and CommandConflictError if the ID was used with different
        contents; in both cases the engine is unchanged.
        If the command's tick was already simulated, history is rewound to the
        newest valid snapshot and replayed through the previous current tick
        before this method returns.
        """
        return self.submit_many([command]) == 1
    def submit_many(self, commands: Iterable[Command]) -> int:
        """Atomically submit a batch with a single replay. Returns the number of
        new (non-duplicate) commands. Any error leaves the engine unchanged."""
        batch = list(commands)
        for command in batch:
            self._validate(command)
        fresh = self._store.plan(batch)
        if not fresh:
            return 0
        self._store.add_many(fresh)
        try:
            self._history.rewind_and_replay(min(c.tick for c in fresh))
        except BaseException:
            self._store.remove_many(fresh)
            raise
        return len(fresh)
    def command(self, command_id: str) -> Command | None:
        return self._store.get(command_id)
    def commands(self) -> tuple[Command, ...]:
        """All stored commands, ascending by (tick, command_id)."""
        return self._store.all_commands()
    # -- time --------------------------------------------------------------
    @property
    def current_tick(self) -> int:
        """Last simulated tick; -1 before anything has been simulated."""
        return self._history.current_tick
    def advance_to(self, tick: int) -> int:
        """Simulate through `tick` inclusive. Targets at or before the current
        tick are a no-op (use world_at to look at the past). Returns current tick."""
        require_tick = type(tick) is int and tick >= 0
        if not require_tick:
            raise TickError(f"target tick must be an int >= 0, got {tick!r}")
        self._history.advance_to(tick)
        return self._history.current_tick
    def step(self) -> int:
        """Simulate exactly one more tick."""
        return self.advance_to(self._history.current_tick + 1)
    # -- queries -----------------------------------------------------------
    def world(self) -> Any:
        """Independent copy of the current world."""
        return self._rules.export_state(self._history.current_state)
    def world_at(self, tick: int) -> Any:
        """Independent copy of the world immediately after `tick`
        (-1 = initial world). Only already-simulated ticks are allowed."""
        return self._rules.export_state(self._history.state_at(tick))
    def hash(self) -> str:
        """SHA-256 hex digest of the canonical encoding of the current world."""
        return self._history.digest_at(self._history.current_tick)
    def hash_at(self, tick: int) -> str:
        return self._history.digest_at(tick)
    # -- instrumentation ---------------------------------------------------
    @property
    def snapshot_interval(self) -> int:
        return self._history.snapshot_interval
    def snapshot_ticks(self) -> tuple[int, ...]:
        return self._history.snapshot_ticks()
    @property
    def stats(self) -> dict[str, int]:
        return {
            "ticks_stepped": self._history.ticks_stepped,
            "rewinds": self._history.rewinds,
            "commands": len(self._store),
        }
__all__ = ["Engine", "INITIAL_TICK"]
