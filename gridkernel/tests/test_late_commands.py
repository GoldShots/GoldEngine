import unittest
from simkernel import CommandConflictError, Engine
from simkernel.games.grid2d import GridRules
from tests.helpers import EAST, NORTH, despawn, make_engine, move, spawn
class LateCommandTests(unittest.TestCase):
    def test_late_blocker_turns_successful_move_into_failure(self):
        e = make_engine(4)
        e.submit_many([spawn("c1", 0, "A", 0, 0), move("c2", 5, "A", *EAST)])
        e.advance_to(8)
        self.assertEqual(e.world_at(5).position_of("A"), (1, 0))
        h_before = e.hash()
        e.submit(spawn("late", 2, "B", 1, 0))     # arrives after tick 5 was simulated
        self.assertEqual(e.current_tick, 8)
        self.assertEqual(e.world_at(4).position_of("A"), (0, 0))
        self.assertEqual(e.world_at(5).position_of("A"), (0, 0))   # move now fails
        self.assertEqual(e.world().to_dict(), {"A": (0, 0), "B": (1, 0)})
        self.assertNotEqual(e.hash(), h_before)
    def test_late_despawn_turns_failure_into_success(self):
        e = make_engine(4)
        e.submit_many([spawn("c1", 0, "A", 0, 0), spawn("c2", 0, "B", 1, 0),
                       move("c3", 3, "A", *EAST)])
        e.advance_to(6)
        self.assertEqual(e.world().position_of("A"), (0, 0))
        e.submit(despawn("late", 1, "B"))
        self.assertEqual(e.world().to_dict(), {"A": (1, 0)})
    def test_late_command_with_smaller_id_changes_which_move_counts(self):
        e = make_engine(4)
        e.submit_many([spawn("c1", 0, "A", 0, 0), move("m5", 2, "A", *EAST)])
        e.advance_to(4)
        self.assertEqual(e.world().position_of("A"), (1, 0))
        e.submit(move("m1", 2, "A", *NORTH))      # smaller ID now wins
        self.assertEqual(e.world().position_of("A"), (0, 1))
    def test_late_command_at_current_tick(self):
        e = make_engine(4)
        e.submit(spawn("c1", 0, "A", 0, 0))
        e.advance_to(4)
        e.submit(move("late", 4, "A", *EAST))
        self.assertEqual(e.world_at(3).position_of("A"), (0, 0))
        self.assertEqual(e.world_at(4).position_of("A"), (1, 0))
    def test_late_command_at_tick_zero(self):
        e = make_engine(4)
        e.advance_to(9)
        e.submit(spawn("late", 0, "A", 3, 3))
        for t in range(0, 10):
            self.assertEqual(e.world_at(t).to_dict(), {"A": (3, 3)})
        self.assertEqual(e.world_at(-1).to_dict(), {})
    def test_future_command_does_not_rewind(self):
        e = make_engine(4)
        e.advance_to(5)
        rewinds, steps = e.stats["rewinds"], e.stats["ticks_stepped"]
        e.submit(spawn("future", 9, "A", 0, 0))
        self.assertEqual(e.stats["rewinds"], rewinds)
        self.assertEqual(e.stats["ticks_stepped"], steps)
        e.advance_to(9)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0)})
    def test_identical_duplicate_is_noop_and_does_not_replay(self):
        e = make_engine(4)
        cmd = spawn("c1", 1, "A", 0, 0)
        self.assertTrue(e.submit(cmd))
        e.advance_to(10)
        h, stats = e.hash(), e.stats
        self.assertFalse(e.submit(spawn("c1", 1, "A", 0, 0)))   # equal, not same object
        self.assertEqual(e.hash(), h)
        self.assertEqual(e.stats, stats)
    def test_conflicting_reuse_raises_and_leaves_engine_unchanged(self):
        e = make_engine(4)
        e.submit(spawn("c1", 1, "A", 0, 0))
        e.advance_to(10)
        h, snaps, stats = e.hash(), e.snapshot_ticks(), e.stats
        for conflicting in (spawn("c1", 1, "A", 9, 9),      # different position
                            spawn("c1", 2, "A", 0, 0),      # different tick
                            move("c1", 1, "A", *EAST)):     # different kind
            with self.subTest(conflicting=conflicting):
                with self.assertRaises(CommandConflictError):
                    e.submit(conflicting)
                self.assertEqual(e.hash(), h)
                self.assertEqual(e.snapshot_ticks(), snaps)
                self.assertEqual(e.stats, stats)
                self.assertEqual(e.command("c1"), spawn("c1", 1, "A", 0, 0))
    def test_conflict_inside_batch_is_atomic(self):
        e = make_engine(4)
        e.advance_to(5)
        h = e.hash()
        with self.assertRaises(CommandConflictError):
            e.submit_many([spawn("a", 1, "A", 0, 0), spawn("b", 1, "B", 1, 1),
                           spawn("a", 1, "A", 7, 7)])
        self.assertIsNone(e.command("a"))
        self.assertIsNone(e.command("b"))
        self.assertEqual(e.hash(), h)
    def test_engine_unchanged_if_rules_fail_during_replay(self):
        class Flaky(GridRules):
            explode_at = None
            def step(self, state, tick, commands):
                if tick == self.explode_at:
                    raise RuntimeError("boom")
                return super().step(state, tick, commands)
        rules = Flaky()
        e = Engine(rules, snapshot_interval=4)
        e.submit(spawn("c1", 0, "A", 0, 0))
        e.advance_to(10)
        h, snaps, stats = e.hash(), e.snapshot_ticks(), e.stats
        rules.explode_at = 7
        with self.assertRaises(RuntimeError):
            e.submit(spawn("late", 3, "B", 1, 1))
        self.assertIsNone(e.command("late"))
        self.assertEqual((e.hash(), e.snapshot_ticks(), e.current_tick), (h, snaps, 10))
        self.assertEqual(e.stats["commands"], stats["commands"])
        with self.assertRaises(RuntimeError):
            rules.explode_at = 12
            e.advance_to(15)
        self.assertEqual((e.hash(), e.current_tick), (h, 10))
        rules.explode_at = None
        e.submit(spawn("late", 3, "B", 1, 1))
        self.assertEqual(e.world().to_dict(), {"A": (0, 0), "B": (1, 1)})
    def test_historical_queries_do_not_change_simulation_or_future(self):
        script = [spawn("c1", 0, "A", 0, 0), spawn("c2", 0, "B", 3, 0)] + \
                 [move(f"m{t}", t, "A", *EAST) for t in range(1, 12)]
        a, b = make_engine(3), make_engine(3, query_cache_size=2)
        for engine in (a, b):
            engine.submit_many(script)
            engine.advance_to(10)
        for t in (9, 2, 5, 0, -1, 7, 10, 3):       # only b is interrogated
            b.world_at(t)
            b.hash_at(t)
        self.assertEqual(a.snapshot_ticks(), b.snapshot_ticks())
        for engine in (a, b):
            engine.submit(spawn("late", 4, "R", 6, 0))
            engine.advance_to(14)
        for t in range(-1, 15):
            self.assertEqual(a.hash_at(t), b.hash_at(t))
    def test_history_before_late_tick_is_unchanged(self):
        e = make_engine(4)
        e.submit_many([spawn("c1", 0, "A", 0, 0)] + [move(f"m{t}", t, "A", *EAST) for t in range(1, 9)])
        e.advance_to(9)
        before = {t: e.hash_at(t) for t in range(-1, 10)}
        e.submit(spawn("late", 5, "B", 6, 0))
        for t in range(-1, 5):
            self.assertEqual(e.hash_at(t), before[t])
        self.assertNotEqual(e.hash_at(5), before[5])
    def test_late_arrival_equals_clean_engine(self):
        commands = [spawn("c1", 0, "A", 0, 0), spawn("c2", 0, "B", 1, 0),
                    move("c3", 2, "A", *EAST), move("c4", 2, "B", *EAST),
                    spawn("c5", 1, "C", 3, 0), despawn("c6", 4, "C"),
                    move("c7", 5, "B", *NORTH)]
        clean = make_engine(3)
        clean.submit_many(commands)
        clean.advance_to(8)
        live = make_engine(3)
        live.submit_many(commands[:2])
        live.advance_to(3)
        live.submit_many(commands[2:4])
        live.advance_to(8)
        live.submit_many(commands[4:])              # all late
        for t in range(-1, 9):
            self.assertEqual(live.hash_at(t), clean.hash_at(t))
            self.assertEqual(live.world_at(t), clean.world_at(t))
    def test_arrival_order_does_not_matter(self):
        import itertools
        commands = [spawn("a", 0, "A", 0, 0), spawn("b", 0, "B", 1, 0),
                    move("c", 1, "A", *EAST), move("d", 1, "B", *EAST),
                    despawn("e", 2, "B")]
        reference = None
        for perm in itertools.permutations(commands):
            e = make_engine(2)
            for i, c in enumerate(perm):
                e.submit(c)
                if i % 2 == 0:
                    e.advance_to(3)
            e.advance_to(3)
            result = [e.hash_at(t) for t in range(-1, 4)]
            if reference is None:
                reference = result
            self.assertEqual(result, reference)
if __name__ == "__main__":
    unittest.main()
