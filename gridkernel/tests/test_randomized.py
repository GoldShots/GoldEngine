import random
import unittest
from tests.helpers import make_engine, oracle_tick, random_commands
SEEDS = range(80)
class RandomizedTests(unittest.TestCase):
    def test_late_arrival_matches_clean_execution(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                commands = random_commands(rng, rng.randint(5, 70), rng.randint(1, 25))
                end = max(c.tick for c in commands) + 2
                clean = make_engine(rng.choice([1, 2, 3, 5, 64]))
                clean.submit_many(commands)
                clean.advance_to(end)
                live = make_engine(rng.choice([1, 2, 3, 4, 7, 64]),
                                   query_cache_size=rng.choice([0, 3, 16]))
                pending = list(commands)
                rng.shuffle(pending)
                while pending:
                    k = rng.randint(1, 5)
                    batch, pending = pending[:k], pending[k:]
                    for c in batch:
                        live.submit(c)
                        if rng.random() < 0.2:
                            live.submit(c)                      # identical duplicate
                    if rng.random() < 0.6:
                        live.advance_to(min(end, live.current_tick + rng.randint(1, 6)))
                    if live.current_tick >= 0 and rng.random() < 0.5:
                        t = rng.randint(-1, live.current_tick)  # historical probing
                        live.world_at(t)
                        live.hash_at(t)
                live.advance_to(end)
                for t in range(-1, end + 1):
                    self.assertEqual(live.hash_at(t), clean.hash_at(t), f"tick {t}")
                    self.assertEqual(live.world_at(t), clean.world_at(t), f"tick {t}")
    def test_engine_matches_independent_oracle_and_invariants(self):
        for seed in range(1000, 1000 + 120):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                commands = random_commands(rng, rng.randint(10, 90), rng.randint(1, 12))
                end = max(c.tick for c in commands)
                engine = make_engine(3)
                engine.submit_many(commands)
                engine.advance_to(end)
                by_tick: dict[int, list] = {}
                for c in commands:
                    by_tick.setdefault(c.tick, []).append(c)
                world: dict = {}
                for t in range(0, end + 1):
                    world = oracle_tick(world, by_tick.get(t, []))
                    actual = engine.world_at(t).to_dict()
                    self.assertEqual(actual, world, f"tick {t}")
                    self.assertEqual(len(set(actual.values())), len(actual),
                                     f"two entities share a cell at tick {t}")
    def test_repeated_late_batches_stay_consistent(self):
        """Feed commands newest-tick-first so nearly every submit is late."""
        for seed in range(2000, 2020):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                commands = random_commands(rng, 40, 15)
                end = 17
                clean = make_engine(4)
                clean.submit_many(commands)
                clean.advance_to(end)
                live = make_engine(4)
                live.advance_to(end)
                for c in sorted(commands, key=lambda c: -c.tick):
                    live.submit(c)
                for t in range(-1, end + 1):
                    self.assertEqual(live.hash_at(t), clean.hash_at(t))
if __name__ == "__main__":
    unittest.main()
