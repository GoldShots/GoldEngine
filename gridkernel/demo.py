"""Demonstration: a late command rewrites the present.
Run from the gridkernel/ directory:  python3 demo.py
"""
from simkernel import CommandConflictError, Engine
from simkernel.games.grid2d import GridRules, move, spawn
def render(world, x_lo=-1, x_hi=8, y=0) -> str:
    by_cell = {pos: name[0].upper() for name, pos in world.entities.items()}
    return "".join(by_cell.get((x, y), ".") for x in range(x_lo, x_hi + 1))
def show(engine, tick, label):
    world = engine.world_at(tick)
    print(f"  {label:<26} tick {tick}: {render(world)}   hash {engine.hash_at(tick)[:16]}")
engine = Engine(GridRules(), snapshot_interval=4)
print("1. Alice walks east each tick toward Bob.")
engine.submit(spawn("c-001", 0, "alice", 0, 0))
engine.submit(spawn("c-002", 0, "bob", 6, 0))
for t in range(1, 7):
    engine.submit(move(f"c-1{t:02d}", t, "alice", 1, 0))
engine.advance_to(6)
print(f"  current tick: {engine.current_tick}")
for t in (0, 2, 5, 6):
    show(engine, t, "before late command")
present_before = engine.hash()
stepped_before = engine.stats["ticks_stepped"]
print("\n2. A LATE command arrives: a rock is spawned at (3,0) during tick 2.")
engine.submit(spawn("c-late", 2, "rock", 3, 0))
print(f"  snapshots now: {engine.snapshot_ticks()}  (ticks >= 2 were invalidated and rebuilt)")
print(f"  ticks replayed: {engine.stats['ticks_stepped'] - stepped_before}  "
      f"(from snapshot at tick 0, not from scratch)")
for t in (0, 1, 2, 5, 6):
    show(engine, t, "after late command")
print(f"  present changed: {present_before != engine.hash()}")
print(f"  alice is now at {engine.world().position_of('alice')}")
print("\n3. A fresh engine that received every command up front agrees.")
fresh = Engine(GridRules(), snapshot_interval=64)
fresh.submit_many(engine.commands())
fresh.advance_to(6)
print(f"  hashes equal for all ticks: "
      f"{all(fresh.hash_at(t) == engine.hash_at(t) for t in range(-1, 7))}")
print("\n4. Resubmitting the identical command is a no-op; a conflicting one is rejected.")
replays = engine.stats["rewinds"]
print(f"  resubmit identical -> new? {engine.submit(spawn('c-late', 2, 'rock', 3, 0))}, "
      f"extra replays: {engine.stats['rewinds'] - replays}")
try:
    engine.submit(spawn("c-late", 2, "rock", 9, 9))
except CommandConflictError as err:
    print(f"  conflicting reuse  -> CommandConflictError: {err}")
print(f"  hash unchanged: {engine.hash() != present_before and engine.hash() == fresh.hash()}")
