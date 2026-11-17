import unittest
from tests.helpers import EAST, NORTH, SOUTH, WEST, resolve
class MovementTests(unittest.TestCase):
    def test_move_into_empty_cell(self):
        self.assertEqual(resolve({"A": (0, 0)}, {"A": EAST}), {"A": (1, 0)})
    def test_chain_into_empty_all_move(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (2, 0)}
        expected = {"A": (1, 0), "B": (2, 0), "C": (3, 0)}
        self.assertEqual(resolve(start, {"A": EAST, "B": EAST, "C": EAST}), expected)
    def test_chain_order_of_command_ids_irrelevant(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (2, 0)}
        moves = {"A": EAST, "B": EAST, "C": EAST}
        self.assertEqual(resolve(start, moves), resolve(start, moves, reverse_ids=True))
    def test_chain_blocked_by_stationary_tail_all_stay(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (2, 0)}
        self.assertEqual(resolve(start, {"A": EAST, "B": EAST}), start)
    def test_swap_succeeds(self):
        start = {"A": (0, 0), "B": (1, 0)}
        self.assertEqual(resolve(start, {"A": EAST, "B": WEST}),
                         {"A": (1, 0), "B": (0, 0)})
    def test_swap_vertical_succeeds(self):
        start = {"A": (0, 0), "B": (0, 1)}
        self.assertEqual(resolve(start, {"A": NORTH, "B": SOUTH}),
                         {"A": (0, 1), "B": (0, 0)})
    def test_four_cycle_rotates(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (1, 1), "D": (0, 1)}
        moves = {"A": EAST, "B": NORTH, "C": WEST, "D": SOUTH}
        self.assertEqual(resolve(start, moves),
                         {"A": (1, 0), "B": (1, 1), "C": (0, 1), "D": (0, 0)})
    def test_six_cycle_rotates(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (2, 0), "D": (2, 1), "E": (1, 1), "F": (0, 1)}
        moves = {"A": EAST, "B": EAST, "C": NORTH, "D": WEST, "E": WEST, "F": SOUTH}
        self.assertEqual(resolve(start, moves),
                         {"A": (1, 0), "B": (2, 0), "C": (2, 1),
                          "D": (1, 1), "E": (0, 1), "F": (0, 0)})
    def test_cycle_with_stationary_member_fails_entirely(self):
        start = {"A": (0, 0), "B": (1, 0), "C": (1, 1), "D": (0, 1)}
        moves = {"A": EAST, "B": NORTH, "C": WEST}  # D does not move
        self.assertEqual(resolve(start, moves), start)
    def test_intruder_into_cycle_breaks_whole_cycle(self):
        # X and D both target (0,0) -> contention -> D fails -> C, B, A fail.
        start = {"A": (0, 0), "B": (1, 0), "C": (1, 1), "D": (0, 1), "X": (-1, 0)}
        moves = {"A": EAST, "B": NORTH, "C": WEST, "D": SOUTH, "X": EAST}
        self.assertEqual(resolve(start, moves), start)
    def test_head_on_collision_into_empty_cell_both_fail(self):
        start = {"A": (0, 0), "B": (2, 0)}
        self.assertEqual(resolve(start, {"A": EAST, "B": WEST}), start)
    def test_three_way_collision_all_fail(self):
        start = {"A": (0, 0), "B": (2, 0), "C": (1, 1)}
        self.assertEqual(resolve(start, {"A": EAST, "B": WEST, "C": SOUTH}), start)
    def test_collision_blocks_follower_chain(self):
        # A and B contend for (1,0); P is behind A, so P is blocked too.
        start = {"P": (-1, 0), "A": (0, 0), "B": (2, 0)}
        self.assertEqual(resolve(start, {"P": EAST, "A": EAST, "B": WEST}), start)
    def test_unrelated_moves_still_succeed_next_to_failures(self):
        start = {"A": (0, 0), "B": (2, 0), "Z": (10, 10)}
        result = resolve(start, {"A": EAST, "B": WEST, "Z": NORTH})
        self.assertEqual(result["A"], (0, 0))
        self.assertEqual(result["B"], (2, 0))
        self.assertEqual(result["Z"], (10, 11))
    def test_chain_feeding_into_vacated_cell_while_rival_contends(self):
        # B leaves (1,0) eastwards, A wants (1,0), C also wants (1,0) -> A, C fail.
        start = {"A": (0, 0), "B": (1, 0), "C": (1, 1)}
        result = resolve(start, {"A": EAST, "B": EAST, "C": SOUTH})
        self.assertEqual(result, {"A": (0, 0), "B": (2, 0), "C": (1, 1)})
    def test_move_into_cell_vacated_by_successful_mover(self):
        start = {"A": (0, 0), "B": (1, 0)}
        self.assertEqual(resolve(start, {"A": EAST, "B": NORTH}),
                         {"A": (1, 0), "B": (1, 1)})
    def test_only_smallest_command_id_move_is_considered(self):
        from tests.helpers import make_engine, move, spawn
        e = make_engine()
        e.submit_many([
            spawn("s1", 0, "A", 0, 0), spawn("s2", 0, "B", 1, 0),
            move("m1", 1, "A", *EAST),    # smallest ID: blocked by stationary B
            move("m2", 1, "A", *NORTH),   # would succeed, but is ignored
        ])
        e.advance_to(1)
        self.assertEqual(e.world().position_of("A"), (0, 0))
    def test_move_of_nonexistent_entity_is_noop(self):
        from tests.helpers import make_engine, move
        e = make_engine()
        e.submit(move("m1", 0, "ghost", *EAST))
        e.advance_to(0)
        self.assertEqual(len(e.world()), 0)
if __name__ == "__main__":
    unittest.main()
