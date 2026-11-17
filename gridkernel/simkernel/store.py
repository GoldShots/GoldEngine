"""Command storage. Knows nothing about simulation or history."""
from __future__ import annotations
from bisect import bisect_left, insort
from collections.abc import Iterable
from .commands import Command
from .errors import CommandConflictError
def _id_of(command: Command) -> str:
    return command.command_id
class CommandStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Command] = {}
        self._by_tick: dict[int, list[Command]] = {}  # each list sorted by command_id
    def __len__(self) -> int:
        return len(self._by_id)
    def get(self, command_id: str) -> Command | None:
        return self._by_id.get(command_id)
    def commands_at(self, tick: int) -> tuple[Command, ...]:
        """Commands for `tick`, ascending by command ID."""
        return tuple(self._by_tick.get(tick, ()))
    def all_commands(self) -> tuple[Command, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda c: (c.tick, c.command_id)))
    def plan(self, commands: Iterable[Command]) -> list[Command]:
        """Return the commands that are genuinely new (deduplicated).
        Raises CommandConflictError if an ID is reused with different contents,
        either against stored commands or within the batch. Does not mutate.
        """
        pending: dict[str, Command] = {}
        for command in commands:
            existing = self._by_id.get(command.command_id)
            if existing is None:
                existing = pending.get(command.command_id)
            if existing is None:
                pending[command.command_id] = command
            elif existing != command:
                raise CommandConflictError(
                    f"command ID {command.command_id!r} already used with different contents"
                )
        return list(pending.values())
    def add_many(self, commands: list[Command]) -> None:
        for command in commands:
            if command.command_id in self._by_id:
                raise CommandConflictError(f"duplicate command ID {command.command_id!r}")
        for command in commands:
            self._by_id[command.command_id] = command
            insort(self._by_tick.setdefault(command.tick, []), command, key=_id_of)
    def remove_many(self, commands: list[Command]) -> None:
        """Roll back a previous add_many."""
        for command in commands:
            self._by_id.pop(command.command_id, None)
            bucket = self._by_tick.get(command.tick)
            if bucket is None:
                continue
            i = bisect_left(bucket, command.command_id, key=_id_of)
            if i < len(bucket) and bucket[i].command_id == command.command_id:
                del bucket[i]
            if not bucket:
                del self._by_tick[command.tick]
