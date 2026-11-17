import unittest
from simkernel import Command, InvalidCommandError, TickError
from simkernel.games.grid2d import Despawn, Move, Spawn
from tests.helpers import EAST, despawn, make_engine, move, spawn
class LifecycleTests(unittest.TestCase):
    def test_initial_world_is_empty_before_tick_zero(self):
        e = make_engine()
        self.assertEqual(e.current_tick, -1)
        self.assertEqual(len(e.world()), 0)
        self.assertEqual(len(e.world_at(-1)), 0)
    def test_spawn_existing_entity_is_noop(self):
        e = make_engine()
        e.submit_many([spawn("c1", 0, "A", 0, 0), spawn("c2", 1, "A", 5, 5)])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0)})
    def test_spawn_into_occupied_cell_is_noop(self):
        e = make_engine()
        e.submit_many([spawn("c1", 0, "A", 0, 0), spawn("c2", 1, "B", 0, 0)])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0)})
    def test_same_tick_spawns_same_cell_smallest_id_wins(self):
        e = make_engine()
        e.submit_many([spawn("c2", 0, "B", 0, 0), spawn("c1", 0, "A", 0, 0)])
        e.advance_to(0)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0)})
    def test_despawn_nonexistent_is_noop(self):
        e = make_engine()
        e.submit(despawn("c1", 0, "ghost"))
        e.advance_to(0)
        self.assertEqual(len(e.world()), 0)
    def test_despawn_and_respawn_same_tick_despawn_runs_first(self):
        e = make_engine()
        e.submit_many([
            spawn("c00", 0, "A", 0, 0),
            spawn("c10", 1, "A", 1, 1),     # smaller ID than the despawn, still later phase
            despawn("c20", 1, "A"),
        ])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (1, 1)})
    def test_despawn_frees_cell_for_spawn_same_tick(self):
        e = make_engine()
        e.submit_many([
            spawn("c00", 0, "A", 0, 0),
            spawn("c01", 1, "B", 0, 0),
            despawn("c02", 1, "A"),
        ])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"B": (0, 0)})
    def test_spawn_then_move_same_tick_uses_post_spawn_world(self):
        e = make_engine()
        e.submit_many([move("c0", 0, "A", *EAST), spawn("c1", 0, "A", 0, 0)])
        e.advance_to(0)
        self.assertEqual(e.world().to_dict(), {"A": (1, 0)})
    def test_move_for_entity_despawned_same_tick_is_noop(self):
        e = make_engine()
        e.submit_many([spawn("c0", 0, "A", 0, 0), move("c1", 1, "A", *EAST),
                       despawn("c2", 1, "A")])
        e.advance_to(1)
        self.assertEqual(len(e.world()), 0)
    def test_respawn_and_move_same_tick(self):
        e = make_engine()
        e.submit_many([spawn("c0", 0, "A", 0, 0), despawn("c1", 1, "A"),
                       spawn("c2", 1, "A", 5, 5), move("c3", 1, "A", *EAST)])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (6, 5)})
    def test_spawn_into_cell_vacated_by_mover_same_tick_fails(self):
        # Spawning happens before movement, so (0,0) is still occupied.
        e = make_engine()
        e.submit_many([spawn("c0", 0, "A", 0, 0), move("c1", 1, "A", *EAST),
                       spawn("c2", 1, "B", 0, 0)])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (1, 0)})
    def test_spawn_into_cell_a_mover_targets_blocks_the_mover(self):
        e = make_engine()
        e.submit_many([spawn("c0", 0, "A", 0, 0), move("c1", 1, "A", *EAST),
                       spawn("c2", 1, "B", 1, 0)])
        e.advance_to(1)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0), "B": (1, 0)})
    def test_entity_id_reuse_after_despawn_at_later_tick(self):
        e = make_engine()
        e.submit_many([spawn("c0", 0, "A", 0, 0), despawn("c1", 1, "A"),
                       spawn("c2", 3, "A", 9, 9)])
        e.advance_to(3)
        self.assertEqual(e.world_at(1).to_dict(), {})
        self.assertEqual(e.world_at(3).to_dict(), {"A": (9, 9)})
class ValidationTests(unittest.TestCase):
    def test_malformed_commands_rejected_without_mutation(self):
        e = make_engine()
        e.submit(spawn("ok", 0, "A", 0, 0))
        e.advance_to(5)
        before = (e.hash(), e.stats["commands"], e.current_tick, e.snapshot_ticks())
        bad = [
            object(), None, "spawn",
            Command("", 0, Spawn("a", 0, 0)),
            Command(5, 0, Spawn("a", 0, 0)),
            Command("\ud800", 0, Spawn("a", 0, 0)),
            Command("x", -1, Spawn("a", 0, 0)),
            Command("x", 1.5, Spawn("a", 0, 0)),
            Command("x", True, Spawn("a", 0, 0)),
            Command("x", "3", Spawn("a", 0, 0)),
            Command("x", 0, None),
            Command("x", 0, "Spawn"),
            Command("x", 0, Spawn("", 0, 0)),
            Command("x", 0, Spawn(1, 0, 0)),
            Command("x", 0, Spawn("a", 0.0, 0)),
            Command("x", 0, Spawn("a", True, 0)),
            Command("x", 0, Spawn("a", 0, None)),
            Command("x", 0, Despawn(None)),
            Command("x", 0, Move("a", 1, 1)),
            Command("x", 0, Move("a", 0, 0)),
            Command("x", 0, Move("a", 2, 0)),
            Command("x", 0, Move("a", 0, -2)),
            Command("x", 0, Move("a", "1", 0)),
        ]
        for command in bad:
            with self.subTest(command=command):
                with self.assertRaises(InvalidCommandError):
                    e.submit(command)
                after = (e.hash(), e.stats["commands"], e.current_tick, e.snapshot_ticks())
                self.assertEqual(before, after)
                self.assertIsNone(e.command("x"))
    def test_batch_with_one_malformed_command_is_entirely_rejected(self):
        e = make_engine()
        e.advance_to(3)
        h = e.hash()
        with self.assertRaises(InvalidCommandError):
            e.submit_many([spawn("g1", 1, "A", 0, 0), Command("g2", 1, Move("A", 3, 3))])
        self.assertIsNone(e.command("g1"))
        self.assertEqual(e.hash(), h)
        self.assertEqual(len(e.world()), 0)
    def test_queries_of_unsimulated_ticks_rejected(self):
        e = make_engine()
        e.advance_to(2)
        for bad in (3, 100, -2, 1.0, "1", True and None):
            with self.subTest(tick=bad):
                with self.assertRaises(TickError):
                    e.world_at(bad)
                with self.assertRaises(TickError):
                    e.hash_at(bad)
    def test_returned_world_cannot_mutate_engine(self):
        e = make_engine()
        e.submit(spawn("c0", 0, "A", 0, 0))
        e.advance_to(3)
        h = e.hash()
        w = e.world()
        with self.assertRaises(TypeError):
            w.entities["B"] = (1, 1)
        w.to_dict()["B"] = (1, 1)
        w._pos["C"] = (2, 2)          # even poking at internals only hurts the copy
        historical = e.world_at(1)
        historical._pos.clear()
        self.assertEqual(e.hash(), h)
        self.assertEqual(e.world().to_dict(), {"A": (0, 0)})
        self.assertEqual(e.world_at(1).to_dict(), {"A": (0, 0)})
if __name__ == "__main__":
    unittest.main()
