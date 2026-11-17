"""Unbounded 2D integer grid game. +y is north, +x is east (convention only)."""
from __future__ import annotations
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from ..canonical import encode_int, encode_str, encode_uvarint
from ..commands import Command, require_int, require_text
from ..errors import InvalidCommandError
from ..rules import Rules
Cell = tuple[int, int]
NORTH: Cell = (0, 1)
SOUTH: Cell = (0, -1)
EAST: Cell = (1, 0)
WEST: Cell = (-1, 0)
_DIRECTIONS = frozenset({NORTH, SOUTH, EAST, WEST})
# ---- actions ---------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Spawn:
    entity_id: str
    x: int
    y: int
@dataclass(frozen=True, slots=True)
class Despawn:
    entity_id: str
@dataclass(frozen=True, slots=True)
class Move:
    entity_id: str
    dx: int
    dy: int
def spawn(command_id: str, tick: int, entity_id: str, x: int, y: int) -> Command:
    return Command(command_id, tick, Spawn(entity_id, x, y))
def despawn(command_id: str, tick: int, entity_id: str) -> Command:
    return Command(command_id, tick, Despawn(entity_id))
def move(command_id: str, tick: int, entity_id: str, dx: int, dy: int) -> Command:
    return Command(command_id, tick, Move(entity_id, dx, dy))
# ---- world -----------------------------------------------------------------
class GridWorld:
    """Read-only view of a grid world: entity ID -> (x, y)."""
    __slots__ = ("_pos", "_cells")
    def __init__(self, positions: Mapping[str, Cell] | None = None) -> None:
        pos = {e: (int(p[0]), int(p[1])) for e, p in (positions or {}).items()}
        if len(set(pos.values())) != len(pos):
            raise ValueError("two entities occupy the same cell")
        self._pos: dict[str, Cell] = pos
        self._cells: dict[Cell, str] | None = None
    @classmethod
    def _wrap(cls, pos: dict[str, Cell]) -> GridWorld:
        world = cls.__new__(cls)
        world._pos = pos
        world._cells = None
        return world
    @property
    def entities(self) -> Mapping[str, Cell]:
        """Read-only mapping entity ID -> (x, y)."""
        return MappingProxyType(self._pos)
    def position_of(self, entity_id: str) -> Cell | None:
        return self._pos.get(entity_id)
    def entity_at(self, x: int, y: int) -> str | None:
        if self._cells is None:
            self._cells = {p: e for e, p in self._pos.items()}
        return self._cells.get((x, y))
    def to_dict(self) -> dict[str, Cell]:
        return dict(self._pos)
    def copy(self) -> GridWorld:
        return GridWorld._wrap(dict(self._pos))
    def __len__(self) -> int:
        return len(self._pos)
    def __contains__(self, entity_id: object) -> bool:
        return entity_id in self._pos
    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._pos))
    def __eq__(self, other: object) -> bool:
        return isinstance(other, GridWorld) and self._pos == other._pos
    def __repr__(self) -> str:
        return f"GridWorld({dict(sorted(self._pos.items()))!r})"
# ---- rules -----------------------------------------------------------------
class GridRules(Rules[GridWorld]):
    name = "grid2d/1"
    def initial_state(self) -> GridWorld:
        return GridWorld._wrap({})
    def validate_action(self, action: object) -> None:
        kind = type(action)
        if kind is Spawn:
            require_text(action.entity_id, "entity_id")
            require_int(action.x, "x")
            require_int(action.y, "y")
        elif kind is Despawn:
            require_text(action.entity_id, "entity_id")
        elif kind is Move:
            require_text(action.entity_id, "entity_id")
            require_int(action.dx, "dx")
            require_int(action.dy, "dy")
            if (action.dx, action.dy) not in _DIRECTIONS:
                raise InvalidCommandError(
                    f"move must be exactly one cell N/S/E/W, got ({action.dx}, {action.dy})"
                )
        else:
            raise InvalidCommandError(f"unknown action type {kind.__name__}")
    def step(self, state: GridWorld, tick: int, commands: Sequence[Command]) -> GridWorld:
        if not commands:
            return state  # states are immutable values; sharing is safe
        ordered = sorted(commands, key=lambda c: c.command_id)
        pos: dict[str, Cell] = dict(state._pos)
        cells: dict[Cell, str] = {p: e for e, p in pos.items()}
        # Phase 1: despawns, ascending command ID.
        for c in ordered:
            a = c.action
            if type(a) is Despawn:
                p = pos.pop(a.entity_id, None)
                if p is not None:
                    del cells[p]
        # Phase 2: spawns, ascending command ID.
        for c in ordered:
            a = c.action
            if type(a) is Spawn:
                cell = (a.x, a.y)
                if a.entity_id in pos or cell in cells:
                    continue
                pos[a.entity_id] = cell
                cells[cell] = a.entity_id
        # Phase 3: moves, resolved against the post-spawn world.
        # Only the smallest-ID move per entity is considered.
        attempts: dict[str, Cell] = {}
        for c in ordered:
            a = c.action
            if type(a) is Move and a.entity_id in pos and a.entity_id not in attempts:
                x, y = pos[a.entity_id]
                attempts[a.entity_id] = (x + a.dx, y + a.dy)
        if attempts:
            into: dict[Cell, list[str]] = {}
            for entity, dest in attempts.items():
                into.setdefault(dest, []).append(entity)
            failed: set[str] = set()
            queue: list[str] = []
            for dest, movers in into.items():
                occupant = cells.get(dest)
                contended = len(movers) > 1  # every entity that *attempts* it fails
                blocked = occupant is not None and occupant not in attempts
                if contended or blocked:
                    for m in movers:
                        if m not in failed:
                            failed.add(m)
                            queue.append(m)
            # A failed entity stays put, so whoever wants its cell fails too.
            # Starting optimistic and only removing necessary failures keeps
            # swaps and longer cycles successful.
            while queue:
                entity = queue.pop()
                for waiter in into.get(pos[entity], ()):
                    if waiter not in failed:
                        failed.add(waiter)
                        queue.append(waiter)
            for entity, dest in attempts.items():
                if entity not in failed:
                    pos[entity] = dest
        return GridWorld._wrap(pos)
    def encode_state(self, state: GridWorld) -> bytes:
        parts = [encode_uvarint(len(state._pos))]
        for entity in sorted(state._pos, key=lambda s: s.encode("utf-8")):
            x, y = state._pos[entity]
            parts.append(encode_str(entity))
            parts.append(encode_int(x))
            parts.append(encode_int(y))
        return b"".join(parts)
    def export_state(self, state: GridWorld) -> GridWorld:
        return state.copy()
