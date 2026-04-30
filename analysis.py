"""
RAF:LAA World Cycle Analysis.

1. Long-term observation  — cycle period stability over N ticks
2. Collapse classification — 4 collapse types
3. Rebirth pattern analysis — post-rebirth Echo/Curvature/Gravity distribution
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from .ast_nodes import Field
from .metrics import WorldMetrics
from .phase import WorldPhase, WorldRebirthRecord


# ── 1. Collapse type classification ──────────────────────────────────────────

class CollapseType(str, Enum):
    PHASE_RUPTURE    = "phase_rupture"     # Echo jump — phase field broken
    GRADIENT_DIVERGE = "gradient_diverge"  # Curvature negative divergence
    GRAVITY_LOSS     = "gravity_loss"      # Gravity too shallow
    MULTI_PHASE      = "multi_phase"       # basin_count spike → cross-group interference
    WORLD_COLLAPSE   = "world_collapse"    # World-level metrics triggered


@dataclass
class CollapseEvent:
    tick:       int
    origin:     Optional[str]            # None = world-level
    type:       CollapseType
    metrics_at: Optional[WorldMetrics]
    meaning:    None = None


def classify_field_collapse(f: Field,
                             prev: Optional[Field],
                             tick: int) -> Optional[CollapseEvent]:
    """Classify why a field collapsed."""
    from .phase import FIELD_COLLAPSE_CURVATURE, FIELD_COLLAPSE_GRAVITY, ECHO_JUMP_THRESHOLD
    from .operators import _symbol_phase

    d = f.basin.drift

    if d.curvature.value < FIELD_COLLAPSE_CURVATURE:
        return CollapseEvent(tick=tick, origin=f.pluis.origin,
                             type=CollapseType.GRADIENT_DIVERGE, metrics_at=None)

    if d.gravity.value > FIELD_COLLAPSE_GRAVITY:
        return CollapseEvent(tick=tick, origin=f.pluis.origin,
                             type=CollapseType.GRAVITY_LOSS, metrics_at=None)

    if prev is not None:
        p_new  = _symbol_phase(d.echo.symbol)
        p_prev = _symbol_phase(prev.basin.drift.echo.symbol)
        raw    = abs(p_new - p_prev) % (2 * math.pi)
        jump   = min(raw, 2 * math.pi - raw)
        if jump > ECHO_JUMP_THRESHOLD:
            return CollapseEvent(tick=tick, origin=f.pluis.origin,
                                 type=CollapseType.PHASE_RUPTURE, metrics_at=None)
    return None


def classify_world_collapse(current: WorldMetrics,
                             prev: WorldMetrics,
                             tick: int) -> Optional[CollapseEvent]:
    """Classify why a world-level collapse was triggered."""
    from .phase import (WORLD_COLLAPSE_RS_DROP, WORLD_COLLAPSE_VAR_SPIKE,
                         WORLD_COLLAPSE_GRAV_RISE, WORLD_COLLAPSE_BASIN_JUMP)

    if current.basin_count - prev.basin_count >= WORLD_COLLAPSE_BASIN_JUMP:
        return CollapseEvent(tick=tick, origin=None,
                             type=CollapseType.MULTI_PHASE, metrics_at=current)

    if current.curvature_var - prev.curvature_var > WORLD_COLLAPSE_VAR_SPIKE:
        return CollapseEvent(tick=tick, origin=None,
                             type=CollapseType.GRADIENT_DIVERGE, metrics_at=current)

    if current.gravity_mean - prev.gravity_mean > WORLD_COLLAPSE_GRAV_RISE:
        return CollapseEvent(tick=tick, origin=None,
                             type=CollapseType.GRAVITY_LOSS, metrics_at=current)

    if current.resonance_mean - prev.resonance_mean < WORLD_COLLAPSE_RS_DROP:
        return CollapseEvent(tick=tick, origin=None,
                             type=CollapseType.WORLD_COLLAPSE, metrics_at=current)

    return None


# ── 2. Rebirth pattern snapshot ────────────────────────────────────────────────

@dataclass
class RebirthPattern:
    tick:              int
    echo_symbols:      list[str]
    curvature_values:  list[float]
    gravity_values:    list[float]
    basin_count:       int
    resonance_mean:    float

    def echo_diversity(self) -> float:
        """Unique echo ratio (1.0 = all different, 0.0 = all same)."""
        if not self.echo_symbols:
            return 0.0
        return len(set(self.echo_symbols)) / len(self.echo_symbols)

    def curvature_spread(self) -> float:
        if len(self.curvature_values) < 2:
            return 0.0
        return statistics.stdev(self.curvature_values)

    def gravity_depth(self) -> float:
        if not self.gravity_values:
            return 0.0
        return statistics.mean(self.gravity_values)


# ── 3. Cycle period tracker ────────────────────────────────────────────────────

@dataclass
class CyclePeriod:
    start_tick: int
    end_tick:   int
    duration:   int
    phase_seq:  list[WorldPhase]


# ── 4. WorldAnalyzer ──────────────────────────────────────────────────────────

class WorldAnalyzer:
    """
    Plugs into WorldClock to track:
    - collapse events (typed)
    - rebirth patterns
    - cycle periods
    """

    def __init__(self):
        self.collapse_events: list[CollapseEvent]   = []
        self.rebirth_patterns: list[RebirthPattern]  = []
        self.cycle_periods: list[CyclePeriod]        = []
        self._last_collapse_tick: Optional[int]      = None
        self._phase_seq: list[WorldPhase]            = []
        self._prev_metrics: Optional[WorldMetrics]   = None

    def record(self,
               world,
               metrics: WorldMetrics,
               current_phase: WorldPhase,
               fields_prev: dict[str, "Field"]) -> None:
        """Call once per tick after phase update."""
        self._phase_seq.append(current_phase)

        # Classify field collapses
        for f in world.map.all():
            prev = fields_prev.get(f.pluis.origin)
            ev = classify_field_collapse(f, prev, metrics.tick)
            if ev:
                self.collapse_events.append(ev)

        # Classify world collapse
        if self._prev_metrics is not None:
            ev = classify_world_collapse(metrics, self._prev_metrics, metrics.tick)
            if ev:
                self.collapse_events.append(ev)

        # Detect rebirth (phase transition to REBIRTH)
        if current_phase == WorldPhase.REBIRTH:
            rp = self._snapshot_rebirth(world, metrics)
            self.rebirth_patterns.append(rp)

        # Track cycle periods (STABILITY → COLLAPSE → REBIRTH → STABILITY)
        self._update_cycles(current_phase, metrics.tick)

        self._prev_metrics = metrics

    def _snapshot_rebirth(self, world, metrics: WorldMetrics) -> RebirthPattern:
        fields = world.map.all()
        return RebirthPattern(
            tick=metrics.tick,
            echo_symbols=[f.basin.drift.echo.symbol for f in fields],
            curvature_values=[f.basin.drift.curvature.value for f in fields],
            gravity_values=[f.basin.drift.gravity.value for f in fields],
            basin_count=metrics.basin_count,
            resonance_mean=metrics.resonance_mean,
        )

    def _update_cycles(self, phase: WorldPhase, tick: int) -> None:
        if len(self._phase_seq) < 2:
            return
        prev = self._phase_seq[-2]
        if prev != WorldPhase.STABILITY and phase == WorldPhase.STABILITY:
            # completed a cycle
            if self._last_collapse_tick is not None:
                self.cycle_periods.append(CyclePeriod(
                    start_tick=self._last_collapse_tick,
                    end_tick=tick,
                    duration=tick - self._last_collapse_tick,
                    phase_seq=list(self._phase_seq[-4:]),
                ))
        if phase == WorldPhase.COLLAPSE and prev != WorldPhase.COLLAPSE:
            self._last_collapse_tick = tick

    def collapse_type_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for ev in self.collapse_events:
            k = ev.type.value
            dist[k] = dist.get(k, 0) + 1
        return dist

    def cycle_period_stats(self) -> dict:
        if not self.cycle_periods:
            return {"count": 0}
        durations = [c.duration for c in self.cycle_periods]
        return {
            "count":  len(durations),
            "mean":   round(statistics.mean(durations), 2),
            "stdev":  round(statistics.stdev(durations), 2) if len(durations) > 1 else 0.0,
            "min":    min(durations),
            "max":    max(durations),
        }

    def rebirth_pattern_stats(self) -> dict:
        if not self.rebirth_patterns:
            return {}
        diversities = [rp.echo_diversity() for rp in self.rebirth_patterns]
        depths      = [rp.gravity_depth()  for rp in self.rebirth_patterns]
        return {
            "rebirths":        len(self.rebirth_patterns),
            "echo_diversity":  round(statistics.mean(diversities), 4),
            "gravity_depth":   round(statistics.mean(depths), 4),
        }

    def plot_collapse_types(self, save_path: Optional[str] = None) -> None:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("[analysis] matplotlib not available.")
            return

        dist = self.collapse_type_distribution()
        if not dist:
            print("[analysis] no collapses recorded.")
            return

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle("Collapse Analysis", fontsize=13)

        # Pie chart
        axes[0].pie(dist.values(), labels=dist.keys(), autopct="%1.1f%%",
                    startangle=90, textprops={"fontsize": 9})
        axes[0].set_title("Collapse Type Distribution")

        # Timeline
        ticks  = [ev.tick for ev in self.collapse_events]
        types  = [ev.type.value for ev in self.collapse_events]
        colors_map = {
            "phase_rupture":    "#e74c3c",
            "gradient_diverge": "#e67e22",
            "gravity_loss":     "#f1c40f",
            "multi_phase":      "#9b59b6",
            "world_collapse":   "#2c3e50",
        }
        colors = [colors_map.get(t, "#95a5a6") for t in types]
        axes[1].scatter(ticks, types, c=colors, s=80, zorder=3)
        axes[1].set_xlabel("tick")
        axes[1].set_title("Collapse Events Timeline")
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"[analysis] saved to {save_path}")
        else:
            plt.show()
        plt.close()
