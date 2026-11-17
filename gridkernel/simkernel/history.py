"""History management: periodic snapshots, rewind/replay, query & hash caches.
Time model
----------
State "after tick t" (t >= 0) is the world once every command with tick <= t
has been applied. Tick -1 (INITIAL_TICK) is the initial world "before tick 0".
Invalidation model
------------------
Everything stored for tick t depends on every command with tick <= t. So when a
command with tick T arrives and T <= current_tick:
  * every snapshot with tick >= T is discarded (snapshot at T included: it was
    computed without the new command),
  * every cached historical state and cached hash with tick >= T is discarded,
  * the newest surviving snapshot (strictly before T, or the initial state) is
    the restore point, and ticks restore+1 .. current_tick are replayed,
    regenerating snapshots at interval boundaries along the way.
Entries for ticks < T are untouched. Commands with T > current_tick invalidate
nothing. The swap-in is done only after replay fully succeeds, so an exception
in the rules leaves the history untouched.
"""
from __future__ import annotations
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from .canonical import sha256_hex
from .errors import ConfigurationError, TickError
from .rules import Rules
from .store import CommandStore
INITIAL_TICK = -1
_HASH_CACHE_MAX = 65536
class History[S]:
    def __init__(
        self,
        rules: Rules[S],
        store: CommandStore,
        *,
        snapshot_interval: int,
        query_cache_size: int,
    ) -> None:
        if type(snapshot_interval) is not int or snapshot_interval < 1:
            raise ConfigurationError("snapshot_interval must be an int >= 1")
        if type(query_cache_size) is not int or query_cache_size < 0:
            raise ConfigurationError("query_cache_size must be an int >= 0")
        if type(getattr(rules, "name", None)) is not str or not rules.name:
            raise ConfigurationError("rules.name must be a non-empty str")
        self._rules = rules
        self._store = store
        self._interval = snapshot_interval
        self._query_cache_size = query_cache_size
        initial = rules.initial_state()
        self._snapshots: dict[int, S] = {INITIAL_TICK: initial}
        self._snapshot_ticks: list[int] = [INITIAL_TICK]  # sorted
        self._current_tick = INITIAL_TICK
        self._current_state: S = initial
        self._query_cache: OrderedDict[int, S] = OrderedDict()  # LRU of replayed states
        self._hash_cache: OrderedDict[int, str] = OrderedDict()  # LRU of digests
        self.ticks_stepped = 0  # total rules.step() calls (for instrumentation/tests)
        self.rewinds = 0        # number of late-command replays
    # -- introspection -----------------------------------------------------
    @property
    def current_tick(self) -> int:
        return self._current_tick
    @property
    def current_state(self) -> S:
        return self._current_state
    @property
    def snapshot_interval(self) -> int:
        return self._interval
    def snapshot_ticks(self) -> tuple[int, ...]:
        return tuple(self._snapshot_ticks)
    # -- internals ---------------------------------------------------------
    def _step(self, state: S, tick: int) -> S:
        self.ticks_stepped += 1
        return self._rules.step(state, tick, self._store.commands_at(tick))
    def _check_tick(self, tick: object) -> int:
        if type(tick) is not int:
            raise TickError(f"tick must be an int, got {type(tick).__name__}")
        if tick < INITIAL_TICK:
            raise TickError(f"tick must be >= {INITIAL_TICK}, got {tick}")
        if tick > self._current_tick:
            raise TickError(
                f"tick {tick} has not been simulated yet (current tick is {self._current_tick})"
            )
        return tick
    def _commit_snapshots(self, staged: dict[int, S]) -> None:
        for t in sorted(staged):
            self._snapshots[t] = staged[t]
            self._snapshot_ticks.append(t)
    def _drop_caches_from(self, tick: int) -> None:
        for cache in (self._query_cache, self._hash_cache):
            for key in [k for k in cache if k >= tick]:
                del cache[key]
    def _best_base(self, tick: int) -> tuple[int, S]:
        """Latest known state at or before `tick` (snapshot or cached query)."""
        i = bisect_right(self._snapshot_ticks, tick) - 1
        base_tick = self._snapshot_ticks[i]
        base_state = self._snapshots[base_tick]
        for cached_tick, cached_state in self._query_cache.items():
            if base_tick < cached_tick <= tick:
                base_tick, base_state = cached_tick, cached_state
        return base_tick, base_state
    # -- mutation ----------------------------------------------------------
    def advance_to(self, target: int) -> None:
        """Simulate through `target` inclusive. All-or-nothing."""
        if target <= self._current_tick:
            return
        state = self._current_state
        staged: dict[int, S] = {}
        for t in range(self._current_tick + 1, target + 1):
            state = self._step(state, t)
            if t % self._interval == 0:
                staged[t] = state
        self._commit_snapshots(staged)
        self._current_tick = target
        self._current_state = state
    def rewind_and_replay(self, earliest_changed_tick: int) -> bool:
        """Call after commands with tick >= earliest_changed_tick were added.
        Restores the newest valid snapshot and replays through the previous
        current tick. Returns False if nothing had been simulated that far.
        All-or-nothing: on exception, history is unchanged.
        """
        if earliest_changed_tick > self._current_tick:
            return False
        cut = bisect_left(self._snapshot_ticks, earliest_changed_tick)
        # cut >= 1 always: INITIAL_TICK (-1) < any command tick (>= 0).
        base_tick = self._snapshot_ticks[cut - 1]
        state = self._snapshots[base_tick]
        staged: dict[int, S] = {}
        for t in range(base_tick + 1, self._current_tick + 1):
            state = self._step(state, t)
            if t % self._interval == 0:
                staged[t] = state
        # Commit (cannot fail past this point).
        for t in self._snapshot_ticks[cut:]:
            del self._snapshots[t]
        del self._snapshot_ticks[cut:]
        self._commit_snapshots(staged)
        self._current_state = state
        self._drop_caches_from(earliest_changed_tick)
        self.rewinds += 1
        return True
    # -- queries -----------------------------------------------------------
    def state_at(self, tick: int) -> S:
        """Internal (shared, do not expose) state after `tick`. Never alters the
        current simulation; may populate the query cache."""
        self._check_tick(tick)
        if tick == self._current_tick:
            return self._current_state
        snap = self._snapshots.get(tick)
        if snap is not None:
            return snap
        cached = self._query_cache.get(tick)
        if cached is not None:
            self._query_cache.move_to_end(tick)
            return cached
        base_tick, state = self._best_base(tick)
        for t in range(base_tick + 1, tick + 1):
            state = self._step(state, t)
        if self._query_cache_size > 0:
            self._query_cache[tick] = state
            while len(self._query_cache) > self._query_cache_size:
                self._query_cache.popitem(last=False)
        return state
    def digest_at(self, tick: int) -> str:
        self._check_tick(tick)
        digest = self._hash_cache.get(tick)
        if digest is not None:
            self._hash_cache.move_to_end(tick)
            return digest
        payload = self._rules.encode_state(self.state_at(tick))
        digest = sha256_hex("simkernel/1/" + self._rules.name, payload)
        self._hash_cache[tick] = digest
        while len(self._hash_cache) > _HASH_CACHE_MAX:
            self._hash_cache.popitem(last=False)
        return digest
