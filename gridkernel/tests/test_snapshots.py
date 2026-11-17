import unittest
from simkernel import ConfigurationError, Engine
from simkernel.games.grid2d import GridRules
from tests.helpers import EAST, make_engine, move, spawn
def seeded_engine(interval, upto=20, **kw):
    e = make_engine(interval, **kw)
    e.submit_many([spawn("c000", 0, "A", 0, 0)] +
                  [move(f"m{t:03d}", t, "A", *EAST) for t in range(1, upto + 1)])
    e.advance_to(upto)
    return e
class SnapshotTests(unittest.TestCase):
    def test_invalid_configuration(self):
        for bad in (0, -1, 1.5, True, "4", None):
            with self.subTest(interval=bad):
                with self.assertRaises(ConfigurationError):
                    Engine(GridRules(), snapshot_interval=bad)
        with self.assertRaises(ConfigurationError):
            Engine(GridRules(), query_cache_size=-1)
    def test_snapshots_taken_at_interval_boundaries_only(self):
        e = make_engine(4)
        e.advance_to(10)
        self.assertEqual(e.snapshot_ticks(), (-1, 0, 4, 8))
    def test_interval_one_and_huge_interval(self):
        e1 = seeded_engine(1, 5)
        self.assertEqual(e1.snapshot_ticks(), (-1, 0, 1, 2, 3, 4, 5))
        e2 = seeded_engine(1000, 5)
        self.assertEqual(e2.snapshot_ticks(), (-1, 0))
    def test_advance_in_pieces_equals_advance_at_once(self):
        a, b = make_engine(4), make_engine(4)
        cmds = [spawn("c", 0, "A", 0, 0)] + [move(f"m{t:02d}", t, "A", *EAST) for t in range(1, 12)]
        a.submit_many(cmds)
        b.submit_many(cmds)
        a.advance_to(11)
        for t in range(0, 12):
            b.advance_to(t)
        self.assertEqual(a.snapshot_ticks(), b.snapshot_ticks())
        self.assertEqual(a.hash(), b.hash())
    def test_late_command_replays_from_snapshot_not_from_zero(self):
        e = seeded_engine(4, 20)
        before = e.stats["ticks_stepped"]
        self.assertEqual(before, 21)
        e.submit(spawn("late", 9, "B", 50, 50))
        # newest snapshot strictly before tick 9 is tick 8 -> replay 9..20
        self.assertEqual(e.stats["ticks_stepped"] - before, 12)
        self.assertEqual(e.snapshot_ticks(), (-1, 0, 4, 8, 12, 16, 20))
    def test_late_command_exactly_on_snapshot_boundary_invalidates_that_snapshot(self):
        e = seeded_engine(4, 20)
        before = e.stats["ticks_stepped"]
        e.submit(spawn("late", 8, "B", 50, 50))
        # snapshot 8 included tick-8 commands; must restore from 4 and replay 5..20
        self.assertEqual(e.stats["ticks_stepped"] - before, 16)
        self.assertEqual(e.world_at(8).position_of("B"), (50, 50))
        self.assertEqual(e.world_at(7).position_of("B"), None)
    def test_late_command_one_tick_after_boundary(self):
        e = seeded_engine(4, 20)
        before = e.stats["ticks_stepped"]
        e.submit(spawn("late", 5, "B", 50, 50))
        self.assertEqual(e.stats["ticks_stepped"] - before, 16)   # from 4: ticks 5..20
    def test_late_command_at_tick_zero_replays_everything(self):
        e = seeded_engine(4, 20)
        before = e.stats["ticks_stepped"]
        e.submit(spawn("late", 0, "B", 50, 50))
        self.assertEqual(e.stats["ticks_stepped"] - before, 21)
    def test_late_command_at_current_tick(self):
        e = seeded_engine(4, 20)
        before = e.stats["ticks_stepped"]
        e.submit(spawn("late", 20, "B", 50, 50))
        self.assertEqual(e.stats["ticks_stepped"] - before, 4)   # from 16: 17..20
        self.assertEqual(e.snapshot_ticks(), (-1, 0, 4, 8, 12, 16, 20))
    def test_historical_query_uses_nearest_snapshot(self):
        e = seeded_engine(4, 20, query_cache_size=0)
        base = e.stats["ticks_stepped"]
        e.world_at(10)                                  # from 8: ticks 9,10
        self.assertEqual(e.stats["ticks_stepped"] - base, 2)
        e.world_at(8)                                   # exact snapshot
        e.world_at(20)                                  # current state
        self.assertEqual(e.stats["ticks_stepped"] - base, 2)
        e.world_at(7)                                   # from 4: ticks 5,6,7
        self.assertEqual(e.stats["ticks_stepped"] - base, 5)
        self.assertEqual(e.snapshot_ticks(), (-1, 0, 4, 8, 12, 16, 20))
    def test_query_cache_is_reused_then_invalidated_by_late_command(self):
        e = seeded_engine(4, 20, query_cache_size=4)
        e.world_at(10)
        base = e.stats["ticks_stepped"]
        e.world_at(10)                                   # served from cache
        self.assertEqual(e.stats["ticks_stepped"], base)
        e.world_at(11)                                   # one step from cached tick 10
        self.assertEqual(e.stats["ticks_stepped"] - base, 1)
        e.submit(spawn("late", 6, "B", 50, 50))          # invalidates cache entries >= 6
        self.assertEqual(e.world_at(10).position_of("B"), (50, 50))
    def test_hash_cache_invalidated_by_late_command(self):
        e = seeded_engine(4, 12)
        h3, h6 = e.hash_at(3), e.hash_at(6)
        self.assertEqual(e.hash_at(6), h6)               # cached value is stable
        e.submit(spawn("late", 4, "B", 50, 50))
        self.assertEqual(e.hash_at(3), h3)                # before the late tick: same
        self.assertNotEqual(e.hash_at(6), h6)             # after: recomputed
        clean = make_engine(4)
        clean.submit_many(e.commands())
        clean.advance_to(12)
        for t in range(-1, 13):
            self.assertEqual(e.hash_at(t), clean.hash_at(t))
    def test_results_independent_of_snapshot_interval(self):
        reference = None
        for interval in (1, 2, 3, 5, 7, 64, 1000):
            e = seeded_engine(interval, 15)
            e.submit(spawn("late", 6, "B", 50, 50))
            e.submit(move("late2", 3, "A", 0, 1))
            result = [e.hash_at(t) for t in range(-1, 16)]
            if reference is None:
                reference = result
            self.assertEqual(result, reference, f"interval={interval}")
if __name__ == "__main__":
    unittest.main()
