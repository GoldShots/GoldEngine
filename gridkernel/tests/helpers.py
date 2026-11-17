"""Shared helpers for tests."""
from __future__ import annotations
import random
from simkernel import Command, Engine
from simkernel.games.grid2d import (
    Despawn, GridRules, Move, Spawn, despawn, move, spawn,
    NORTH, SOUTH, EAST, WEST,
)
__all__ = [
    "NORTH", "SOUTH", "EAST", "WEST", "spawn", "despawn", "move",
    "make_engine", "resolve", "random_commands", "oracle_tick",
]
def make_engine(interval: int = 4, **kwargs) -> Engine:
    return Engine(GridRules(), snapshot_interval=interval, **kwargs)
def resolve(start: dict, moves: dict, *, reverse_ids: bool = False) -> dict:
    """Spawn `start` at tick 0, apply one move per entity at tick 1, return the
    world after tick 1 as {entity: (x, y)}."""
    engine = make_engine(4)
    commands = [spawn(f"s{i:03d}", 0, e, *p) for i, (e, p) in enumerate(sorted(start.items()))]
    names = list(moves)
    if reverse_ids:
        names.reverse()
    commands += [move(f"m{i:03d}", 1, e, *moves[e]) for i, e in enumerate(names)]
    engine.submit_many(commands)
    engine.advance_to(1)
    return engine.world().to_dict()
def random_commands(rng: random.Random, count: int, max_tick: int) -> list[Command]:
    """Dense random commands (small pool, small area) to provoke collisions."""
    entities = [f"e{i}" for i in range(7)]
    commands = []
    for i in range(count):
        cid = f"{rng.getrandbits(24):06x}-{i}"  # random order relative to tick/arrival
        tick = rng.randint(0, max_tick)
        entity = rng.choice(entities)
        roll = rng.random()
        if roll < 0.30:
            commands.append(spawn(cid, tick, entity, rng.randint(-2, 2), rng.randint(-2, 2)))
        elif roll < 0.40:
            commands.append(despawn(cid, tick, entity))
        else:
            dx, dy = rng.choice([NORTH, SOUTH, EAST, WEST])
            commands.append(move(cid, tick, entity, dx, dy))
    return commands
def oracle_tick(world: dict, commands: list[Command]) -> dict:
    """Independent brute-force reference for one tick of grid rules.
    Deliberately structured differently from GridRules.step: it starts with
    every attempted move marked successful and repeatedly knocks out moves that
    violate the definition until nothing changes.
    """
    world = dict(world)
    ordered = sorted(commands, key=lambda c: c.command_id)
    for c in ordered:
        if isinstance(c.action, Despawn):
            world.pop(c.action.entity_id, None)
    for c in ordered:
        a = c.action
        if isinstance(a, Spawn):
            if a.entity_id not in world and (a.x, a.y) not in world.values():
                world[a.entity_id] = (a.x, a.y)
    attempts: dict = {}
    for c in ordered:
        a = c.action
        if isinstance(a, Move) and a.entity_id in world and a.entity_id not in attempts:
            px, py = world[a.entity_id]
            attempts[a.entity_id] = (px + a.dx, py + a.dy)
    ok = set(attempts)
    changed = True
    while changed:
        changed = False
        for e in sorted(ok):
            dest = attempts[e]
            rivals = [o for o in attempts if o != e and attempts[o] == dest]
            occupant = next((o for o, p in world.items() if p == dest), None)
            blocked = occupant is not None and occupant not in ok
            if rivals or blocked:
                ok.discard(e)
                changed = True
    for e in ok:
        world[e] = attempts[e]
    return world
