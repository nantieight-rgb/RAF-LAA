"""
RAF:LAA World Metrics — Stability Dynamics Observability.

Compresses world state per tick into scalar indicators:
  resonance_mean  — synchronization degree (↑ = converging)
  curvature_var   — spread of drift directions (→ 0 = stabilized)
  gravity_mean    — average basin depth (↓ = world settling)
  basin_count     — distinct Echo groups (↓ = single field, = = multi-phase stable)

Also tracks per-Field trajectory (curvature / gravity / echo history).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .ast_nodes import Field
from .dynamics import resonance_strength
from .world import World


# ── World-level scalar ────────────────────────────────────────────────────────

@dataclass
class WorldMetrics:
    tick:           int
    resonance_mean: float
    curvature_var:  float
    gravity_mean:   float
    basin_count:    int
    field_count:    int
    meaning:        None = None   # always None

    def __str__(self) -> str:
        return (
            f"tick={self.tick:3d} | "
            f"rs_mean={self.resonance_mean:+.4f} | "
            f"curv_var={self.curvature_var:.4f} | "
            f"grav_mean={self.gravity_mean:+.4f} | "
            f"basins={self.basin_count} | "
            f"fields={self.field_count}"
        )


def measure_world(world: World, tick: int) -> WorldMetrics:
    fields = world.map.all()
    if not fields:
        return WorldMetrics(tick, 0.0, 0.0, 0.0, 0, 0)

    # resonance_mean — all pairs
    rs_vals = []
    for i in range(len(fields)):
        for j in range(i + 1, len(fields)):
            rs_vals.append(resonance_strength(fields[i], fields[j]))
    resonance_mean = sum(rs_vals) / len(rs_vals) if rs_vals else 0.0

    # curvature_var
    curvs = [f.basin.drift.curvature.value for f in fields]
    c_mean = sum(curvs) / len(curvs)
    curvature_var = sum((c - c_mean) ** 2 for c in curvs) / len(curvs)

    # gravity_mean
    gravs = [f.basin.drift.gravity.value for f in fields]
    gravity_mean = sum(gravs) / len(gravs)

    # basin_count (distinct Echo symbols)
    basin_count = len({f.basin.drift.echo.symbol for f in fields})

    return WorldMetrics(
        tick=tick,
        resonance_mean=resonance_mean,
        curvature_var=curvature_var,
        gravity_mean=gravity_mean,
        basin_count=basin_count,
        field_count=len(fields),
    )


# ── Per-Field trajectory ──────────────────────────────────────────────────────

@dataclass
class FieldTrajectory:
    origin:           str
    curvature_history: list[float] = field(default_factory=list)
    gravity_history:   list[float] = field(default_factory=list)
    echo_history:      list[str]   = field(default_factory=list)

    def record(self, f: Field) -> None:
        self.curvature_history.append(f.basin.drift.curvature.value)
        self.gravity_history.append(f.basin.drift.gravity.value)
        self.echo_history.append(f.basin.drift.echo.symbol)

    def convergence_rate(self) -> Optional[float]:
        """Rate of Curvature change (last step / first step). None if < 2 points."""
        if len(self.curvature_history) < 2:
            return None
        first = self.curvature_history[0]
        last  = self.curvature_history[-1]
        if abs(first) < 1e-9:
            return 0.0
        return (abs(first) - abs(last)) / abs(first)


# ── MetricsLogger ─────────────────────────────────────────────────────────────

class MetricsLogger:
    """
    Attaches to a WorldClock and logs metrics + trajectories per tick.
    """

    def __init__(self):
        self.world_log:  list[WorldMetrics]               = []
        self.trajectories: dict[str, FieldTrajectory]     = {}

    def record(self, world: World, tick: int) -> WorldMetrics:
        m = measure_world(world, tick)
        self.world_log.append(m)

        for f in world.map.all():
            o = f.pluis.origin
            if o not in self.trajectories:
                self.trajectories[o] = FieldTrajectory(origin=o)
            self.trajectories[o].record(f)

        return m

    def summary(self) -> str:
        if not self.world_log:
            return "(no data)"
        first, last = self.world_log[0], self.world_log[-1]
        lines = [
            f"Ticks recorded : {len(self.world_log)}",
            f"resonance_mean : {first.resonance_mean:+.4f} → {last.resonance_mean:+.4f}",
            f"curvature_var  : {first.curvature_var:.4f} → {last.curvature_var:.4f}",
            f"gravity_mean   : {first.gravity_mean:+.4f} → {last.gravity_mean:+.4f}",
            f"basin_count    : {first.basin_count} → {last.basin_count}",
        ]
        return "\n".join(lines)

    def plot(self, save_path: Optional[str] = None) -> None:
        """
        Plot world metrics over time using matplotlib.
        If save_path is given, saves to file instead of showing.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("[metrics] matplotlib not available — skipping plot.")
            return

        ticks = [m.tick for m in self.world_log]
        fig, axes = plt.subplots(2, 2, figsize=(10, 7))
        fig.suptitle("BandOS World Stability Dynamics", fontsize=13)

        def _plot(ax, values, label, color, hline=None):
            ax.plot(ticks, values, color=color, linewidth=1.8)
            if hline is not None:
                ax.axhline(hline, color="gray", linestyle="--", linewidth=0.8)
            ax.set_title(label, fontsize=10)
            ax.set_xlabel("tick")
            ax.grid(True, alpha=0.3)

        _plot(axes[0][0],
              [m.resonance_mean for m in self.world_log],
              "resonance_mean (↑ = converging)", "#3a7bd5", hline=1.0)
        _plot(axes[0][1],
              [m.curvature_var for m in self.world_log],
              "curvature_var (→ 0 = stabilized)", "#e55d87", hline=0.0)
        _plot(axes[1][0],
              [m.gravity_mean for m in self.world_log],
              "gravity_mean (↓ = deepening)", "#44aa88", hline=-1.0)
        _plot(axes[1][1],
              [m.basin_count for m in self.world_log],
              "basin_count (distinct Echo groups)", "#f5a623")

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"[metrics] saved to {save_path}")
        else:
            plt.show()
        plt.close()

    def plot_trajectories(self, save_path: Optional[str] = None) -> None:
        """Plot per-Field Curvature trajectories."""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.cm as cm
        except ImportError:
            print("[metrics] matplotlib not available.")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle("Field Trajectories", fontsize=13)
        colors = cm.tab10.colors

        for idx, (origin, traj) in enumerate(self.trajectories.items()):
            c = colors[idx % len(colors)]
            label = origin[:8]
            ax1.plot(traj.curvature_history, color=c, label=label, linewidth=1.5)
            ax2.plot(traj.gravity_history, color=c, label=label, linewidth=1.5)

        ax1.set_title("Curvature over time"); ax1.set_xlabel("tick")
        ax1.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        ax1.legend(fontsize=7); ax1.grid(True, alpha=0.3)

        ax2.set_title("Gravity over time"); ax2.set_xlabel("tick")
        ax2.axhline(-1, color="gray", linestyle="--", linewidth=0.8)
        ax2.legend(fontsize=7); ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"[metrics] saved to {save_path}")
        else:
            plt.show()
        plt.close()
