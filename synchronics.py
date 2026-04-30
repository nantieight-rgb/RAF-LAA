"""
RAF:LAA World Synchronics — Global Resonance Engine.

Runs one full world tick:
  1. Snapshot  — capture current state (no partial updates)
  2. Pairwise  — apply inter-Field dynamics (interact)
  3. Individual— apply per-Field operators (stabilize, collapse check)
  4. Rebirth   — Fields that collapsed get reborn (PES advances)
  5. PSL       — normalize + verify all Fields
  6. Commit    — push everything to World (map + graph)

After each tick the World holds a fully coherent, PSL-valid state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ast_nodes import Field
from .operators import stabilize, collapse as op_collapse, rebirth as op_rebirth
from .pluis_token import PluisKeyPair
from .psl_normalize import psl_normalize, PSLRejection
from .world import World
from .dynamics import resonance_strength, interact
from .metrics import MetricsLogger, WorldMetrics
from .phase import PhaseTracker, WorldPhase
from .analysis import WorldAnalyzer

# Thresholds
COLLAPSE_TRIGGER  = 1.0   # |curvature| >= this after dynamics → force collapse
REBIRTH_AFTER_COLLAPSE = True


@dataclass
class TickReport:
    """Summary of what happened in one world tick."""
    tick:           int
    field_count:    int
    resonances:     dict[str, float]   # pair label → strength
    collapses:      list[str]          # origins that collapsed
    rebirths:       list[str]          # origins that were reborn
    psl_rejections: list[str]          # origins PSL rejected (removed from world)
    meaning:        None = None        # always None


class WorldClock:
    """
    Drives the world forward tick by tick.

    Usage:
        clock = WorldClock(world, key_pair)
        report = clock.tick()
    """

    def __init__(self, world: World, key_pair: PluisKeyPair):
        self._world    = world
        self._key      = key_pair
        self._tick_n   = 0
        self._last_pes = 0.0
        self.logger    = MetricsLogger()
        self.phase     = PhaseTracker()
        self.analyzer  = WorldAnalyzer()

    @property
    def tick_number(self) -> int:
        return self._tick_n

    def tick(self) -> TickReport:
        self._tick_n += 1
        world   = self._world
        key     = self._key
        origins = [f.pluis.origin for f in world.map.all()]

        # ── Step 1: Snapshot ───────────────────────────────────────────────
        current: dict[str, Field] = {o: world.map.get(o) for o in origins}
        resonances:     dict[str, float] = {}
        collapses:      list[str]        = []
        rebirths:       list[str]        = []
        psl_rejections: list[str]        = []

        # ── Step 2: Pairwise interaction ───────────────────────────────────
        ors = list(origins)
        for i in range(len(ors)):
            for j in range(i + 1, len(ors)):
                o1, o2 = ors[i], ors[j]
                f1, f2 = current[o1], current[o2]
                rs     = resonance_strength(f1, f2)
                label  = f"{o1[:6]}↔{o2[:6]}"
                resonances[label] = round(rs, 4)
                new_f1, new_f2 = interact(f1, f2, key)
                current[o1] = new_f1
                current[o2] = new_f2

        # ── Step 3: Individual dynamics (stabilize) ────────────────────────
        for o in ors:
            current[o] = stabilize(current[o], key)

        # ── Step 4: Collapse detection + rebirth ───────────────────────────
        for o in ors:
            f = current[o]
            if abs(f.basin.drift.curvature.value) >= COLLAPSE_TRIGGER:
                collapsed = op_collapse(f, key)
                collapses.append(o)
                if REBIRTH_AFTER_COLLAPSE:
                    reborn = op_rebirth(collapsed, key)
                    current[o] = reborn
                    rebirths.append(o)
                else:
                    current[o] = collapsed

        # ── Step 5: PSL normalization ──────────────────────────────────────
        for o in list(ors):
            f = current[o]
            try:
                result = psl_normalize(f, key, last_pes=self._last_pes)
                current[o] = result.field
                # Advance last_pes tracker
                if result.field.pes_timestamp > self._last_pes:
                    self._last_pes = result.field.pes_timestamp
            except PSLRejection:
                psl_rejections.append(o)
                current.pop(o, None)
                world.map.remove(o)

        # ── Step 6: Commit ─────────────────────────────────────────────────
        for o, new_f in current.items():
            old = world.map.get(o)
            if old is not None:
                world.apply(old, new_f)

        # ── Step 7: Log metrics + phase update + analysis ─────────────────
        metrics = self.logger.record(world, self._tick_n)
        fields_prev = {o: world.map.get(o) for o in origins}
        self.phase.update(metrics, world, key)
        self.analyzer.record(world, metrics, self.phase.current_phase, fields_prev)

        return TickReport(
            tick=self._tick_n,
            field_count=len(world.map),
            resonances=resonances,
            collapses=collapses,
            rebirths=rebirths,
            psl_rejections=psl_rejections,
        )

    def run(self, ticks: int) -> list[TickReport]:
        """Run multiple ticks, return all reports."""
        return [self.tick() for _ in range(ticks)]
