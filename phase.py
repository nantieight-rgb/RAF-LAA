"""
RAF:LAA World Phase Engine — Collapse / Rebirth Cycle.

Three phases:
  STABILITY  — resonance converging, curvature settled
  COLLAPSE   — structural breakdown, field decay
  REBIRTH    — PES advances, world reconstructed from traces

Phase transitions are detected from WorldMetrics and applied
at the World level via WorldClock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from .ast_nodes import Field, Basin, Drift, Curvature, Echo, Gravity
from .operators import rebirth as op_rebirth
from .pluis_token import PluisKeyPair, inherit
from .world import World
from .metrics import WorldMetrics


# ── Phase enum ────────────────────────────────────────────────────────────────

class WorldPhase(str, Enum):
    STABILITY = "STABILITY"
    COLLAPSE  = "COLLAPSE"
    REBIRTH   = "REBIRTH"


# ── Individual Field collapse conditions ──────────────────────────────────────

FIELD_COLLAPSE_CURVATURE = -0.2   # curvature < this → collapse trigger
FIELD_COLLAPSE_GRAVITY   = -0.05  # gravity > this  → stability lost
ECHO_JUMP_THRESHOLD      = math.pi * 0.8  # phase jump > this → phase rupture


def field_should_collapse(f: Field,
                           prev: Optional[Field] = None) -> bool:
    """
    Check if a single Field should enter collapse.
    prev: previous state (for echo jump detection).
    """
    d = f.basin.drift

    # Condition 1: Curvature negative divergence
    if d.curvature.value < FIELD_COLLAPSE_CURVATURE:
        return True

    # Condition 2: Gravity too shallow (stability lost)
    if d.gravity.value > FIELD_COLLAPSE_GRAVITY:
        return True

    # Condition 3: Echo phase rupture
    if prev is not None:
        from .operators import _symbol_phase
        p_new  = _symbol_phase(d.echo.symbol)
        p_prev = _symbol_phase(prev.basin.drift.echo.symbol)
        raw = abs(p_new - p_prev) % (2 * math.pi)
        jump = min(raw, 2 * math.pi - raw)
        if jump > ECHO_JUMP_THRESHOLD:
            return True

    return False


def collapse_field(f: Field, key_pair: PluisKeyPair) -> Field:
    """
    Execute 3-step field collapse:
      1. Drift reset (curvature=0, gravity=-0.2)
      2. Echo nullification
      3. Rebirth (PES advances, origin preserved)
    """
    from .operators import _rebuild

    # Step 1+2: Drift collapse + Echo nullification
    collapsed = _rebuild(f, key_pair,
                         curvature=0.0,
                         echo_symbol="NullEcho",
                         gravity=-0.2,
                         advance_pes=False)

    # Step 3: Rebirth — PES advances, origin continues
    reborn = op_rebirth(collapsed, key_pair)
    return reborn


# ── World-level collapse detection ────────────────────────────────────────────

# Thresholds for world-phase transition
WORLD_COLLAPSE_RS_DROP    = -0.15  # resonance_mean drop per tick
WORLD_COLLAPSE_VAR_SPIKE  = 0.05   # curvature_var spike
WORLD_COLLAPSE_GRAV_RISE  = 0.2    # gravity_mean rise (shallowing)
WORLD_COLLAPSE_BASIN_JUMP = 2      # basin_count sudden increase


def world_should_collapse(current: WorldMetrics,
                           prev: Optional[WorldMetrics]) -> bool:
    """
    Detect world-level collapse from metrics delta.
    """
    if prev is None:
        return False

    # resonance_mean drop
    if current.resonance_mean - prev.resonance_mean < WORLD_COLLAPSE_RS_DROP:
        return True

    # curvature_var spike
    if current.curvature_var - prev.curvature_var > WORLD_COLLAPSE_VAR_SPIKE:
        return True

    # gravity_mean rising (shallowing = destabilizing)
    if current.gravity_mean - prev.gravity_mean > WORLD_COLLAPSE_GRAV_RISE:
        return True

    # basin_count sudden jump
    if current.basin_count - prev.basin_count >= WORLD_COLLAPSE_BASIN_JUMP:
        return True

    return False


# ── World Rebirth ─────────────────────────────────────────────────────────────

@dataclass
class WorldRebirthRecord:
    tick:     int
    reason:   str
    reborn:   list[str]   # origins reborn
    meaning:  None = None


def world_rebirth(world: World,
                  key_pair: PluisKeyPair,
                  tick: int,
                  reason: str = "world_collapse") -> WorldRebirthRecord:
    """
    Rebirth all Fields in the World.
    Origin preserved, PES advances for all.
    FieldGraph records each transition.
    """
    reborn_origins = []
    for old in world.map.all():
        new = collapse_field(old, key_pair)
        world.apply(old, new)
        reborn_origins.append(new.pluis.origin)

    return WorldRebirthRecord(tick=tick, reason=reason, reborn=reborn_origins)


# ── Phase tracker ─────────────────────────────────────────────────────────────

@dataclass
class PhaseTracker:
    """
    Tracks world phase across ticks and records transitions.
    Plug into WorldClock to get phase-aware behavior.
    """
    current_phase: WorldPhase = WorldPhase.STABILITY
    history: list[tuple[int, WorldPhase]] = field(default_factory=list)
    rebirth_records: list[WorldRebirthRecord] = field(default_factory=list)
    _prev_metrics: Optional[WorldMetrics] = field(default=None, repr=False)

    def update(self,
               metrics: WorldMetrics,
               world: World,
               key_pair: PluisKeyPair) -> WorldPhase:
        """
        Given current metrics, determine and apply phase transition.
        Returns the current phase after update.
        """
        # Check per-field collapse conditions
        field_collapses: list[str] = []
        for f in world.map.all():
            if field_should_collapse(f):
                field_collapses.append(f.pluis.origin)

        if field_collapses:
            self._enter(WorldPhase.COLLAPSE, metrics.tick)
            for origin in field_collapses:
                old = world.map.get(origin)
                if old:
                    new = collapse_field(old, key_pair)
                    world.apply(old, new)
            self._enter(WorldPhase.REBIRTH, metrics.tick)
            self._enter(WorldPhase.STABILITY, metrics.tick)

        # World-level collapse
        elif world_should_collapse(metrics, self._prev_metrics):
            self._enter(WorldPhase.COLLAPSE, metrics.tick)
            rec = world_rebirth(world, key_pair, metrics.tick,
                                reason="world_metrics_collapse")
            self.rebirth_records.append(rec)
            self._enter(WorldPhase.REBIRTH, metrics.tick)
            self._enter(WorldPhase.STABILITY, metrics.tick)

        self._prev_metrics = metrics
        return self.current_phase

    def _enter(self, phase: WorldPhase, tick: int) -> None:
        if phase != self.current_phase:
            self.history.append((tick, phase))
            self.current_phase = phase

    def phase_log(self) -> str:
        if not self.history:
            return "no transitions"
        return " → ".join(f"tick{t}:{p.value}" for t, p in self.history)
