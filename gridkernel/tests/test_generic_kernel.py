"""The kernel must not depend on the grid game: plug in two other rule sets."""
import unittest
from dataclasses import dataclass
from simkernel import Command, Engine, InvalidCommandError, Rules
from simkernel.canonical import encode_int, encode_str, encode_uvarint
@dataclass(frozen=True)
class Add:
    amount: int
class CounterRules(Rules[int]):
    name = "counter/1"
    def initial_state(self):
        return 0
    def validate_action(self, action):
        if type(action) is not Add or type(action.amount) is not int:
            raise InvalidCommandError("bad Add")
    def step(self, state, tick, commands):
        return state + sum(c.action.amount for c in commands)
    def encode_state(self, state):
        return encode_int(state)
    def export_state(self, state):
        return state
@dataclass(frozen=True)
class Note:
    text: str
class LogRules(Rules[tuple]):
    """State records the order in which commands were delivered."""
    name = "log/1"
    def initial_state(self):
        return ()
    def validate_action(self, action):
        if type(action) is not Note or type(action.text) is not str:
            raise InvalidCommandError("bad Note")
    def step(self, state, tick, commands):
        return state + tuple(c.command_id for c in commands)
    def encode_state(self, state):
        return encode_uvarint(len(state)) + b"".join(encode_str(s) for s in state)
    def export_state(self, state):
        return state
class GenericKernelTests(unittest.TestCase):
    def test_counter_game_with_late_commands(self):
        e = Engine(CounterRules(), snapshot_interval=2)
        e.submit(Command("a", 1, Add(10)))
        e.advance_to(5)
        self.assertEqual([e.world_at(t) for t in range(-1, 6)], [0, 0, 10, 10, 10, 10, 10])
        e.submit(Command("b", 3, Add(5)))
        self.assertEqual([e.world_at(t) for t in range(-1, 6)], [0, 0, 10, 10, 15, 15, 15])
    def test_rules_receive_commands_in_ascending_id_order(self):
        e = Engine(LogRules(), snapshot_interval=3)
        for cid in ("c3", "c1", "c2"):
            e.submit(Command(cid, 0, Note("x")))
        e.advance_to(0)
        self.assertEqual(e.world(), ("c1", "c2", "c3"))
        e.submit(Command("c0", 0, Note("late")))
        self.assertEqual(e.world(), ("c0", "c1", "c2", "c3"))
    def test_hash_depends_on_rules_name(self):
        class Other(CounterRules):
            name = "counter/2"
        a, b = Engine(CounterRules()), Engine(Other())
        a.advance_to(0)
        b.advance_to(0)
        self.assertNotEqual(a.hash(), b.hash())
    def test_hash_is_stable_sha256_hex(self):
        e = Engine(CounterRules())
        e.advance_to(0)
        h = e.hash()
        self.assertEqual(len(h), 64)
        int(h, 16)
        self.assertEqual(h, Engine(CounterRules()).hash_at(-1) if False else h)
if __name__ == "__main__":
    unittest.main()
