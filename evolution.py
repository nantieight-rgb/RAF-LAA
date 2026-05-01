"""
RAF:LAA Evolution Engine.

Four evolution mechanisms:
  1. Echo Mutation    — phase drift from disturbance
  2. Drift Evolution  — Curvature baseline shifts with lineage depth
  3. Basin Morphing   — Basin shape changes with collapse history
  4. Adaptive Stability — resilience diverges across Fields
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional

from .ast_nodes import Field
from .operators import _rebuild, _symbol_phase
from .pluis_token import PluisKeyPair
from .world import World


# ── Evolution parameters ──────────────────────────────────────────────────────

ECHO_MUTATION_RATE    = 0.03   # phase shift per disturbance unit
DRIFT_EVOLUTION_RATE  = 0.02   # curvature baseline change per lineage step
BASIN_MORPH_RATE      = 0.05   # gravity deepening per collapse survived
RESILIENCE_DIVERGE    = 0.01   # resilience difference per tick


# ── 1. Echo Mutation ──────────────────────────────────────────────────────────

def _phase_to_echo(phase: float) -> str:
    """Convert a phase value to an S-Unit symbol (deterministic)."""
    normalized = int((phase % (2 * math.pi)) / (2 * math.pi) * 0xFFFFFFFF)
    return f"S{normalized}"


def echo_mutate(f: Field,
                disturbance: float,
                key_pair: PluisKeyPair) -> Field:
    """
    Slightly shift Echo phase based on disturbance strength.
    Small disturbances → small drift. Large → bigger jump.
    """
    current_phase = _symbol_phase(f.basin.drift.echo.symbol)
    delta         = disturbance * ECHO_MUTATION_RATE * (1 if disturbance > 0 else -1)
    new_phase     = (current_phase + delta) % (2 * math.pi)
    new_echo      = _phase_to_echo(new_phase)

    return _rebuild(f, key_pair,
                    curvature=f.basin.drift.curvature.value,
                    echo_symbol=new_echo,
                    gravity=f.basin.drift.gravity.value)


# ── 2. Drift Evolution ────────────────────────────────────────────────────────

def drift_evolve(f: Field,
                 lineage: list[Field],
                 key_pair: PluisKeyPair) -> Field:
    """
    Curvature baseline shifts with lineage depth.
    Deeper lineage → baseline drifts toward the mean of past states.
    """
    if len(lineage) < 2:
        return f

    past_curvatures = [s.basin.drift.curvature.value for s in lineage]
    mean_curv = statistics.mean(past_curvatures)

    current = f.basin.drift.curvature.value
    # Drift toward lineage mean (inertia effect)
    evolved = current + DRIFT_EVOLUTION_RATE * (mean_curv - current)

    return _rebuild(f, key_pair,
                    curvature=evolved,
                    echo_symbol=f.basin.drift.echo.symbol,
                    gravity=f.basin.drift.gravity.value)


# ── 3. Basin Morphing ─────────────────────────────────────────────────────────

def basin_morph(f: Field,
                collapses_survived: int,
                key_pair: PluisKeyPair) -> Field:
    """
    Basin deepens with each collapse survived.
    More collapses → deeper Gravity (more stable attractor).
    """
    current_grav = f.basin.drift.gravity.value
    # Each survived collapse deepens the basin
    deepened = current_grav - collapses_survived * BASIN_MORPH_RATE
    deepened = max(-1.0, deepened)

    return _rebuild(f, key_pair,
                    curvature=f.basin.drift.curvature.value,
                    echo_symbol=f.basin.drift.echo.symbol,
                    gravity=deepened)


# ── 4. Adaptive Stability ─────────────────────────────────────────────────────

@dataclass
class ResilienceProfile:
    origin:            str
    collapses_survived: int = 0
    ticks_stable:      int = 0
    resilience_score:  float = 0.5   # [0, 1] — 0=fragile, 1=robust

    def update(self, collapsed: bool) -> None:
        if collapsed:
            self.collapses_survived += 1
            # Each collapse either strengthens or weakens based on history
            if self.collapses_survived <= 3:
                self.resilience_score = min(1.0,
                    self.resilience_score + RESILIENCE_DIVERGE * 2)
            else:
                self.resilience_score = max(0.0,
                    self.resilience_score - RESILIENCE_DIVERGE)
        else:
            self.ticks_stable += 1
            self.resilience_score = min(1.0,
                self.resilience_score + RESILIENCE_DIVERGE * 0.5)


class AdaptiveStabilityTracker:
    """Tracks resilience profile per Field origin."""

    def __init__(self):
        self._profiles: dict[str, ResilienceProfile] = {}

    def get_or_create(self, origin: str) -> ResilienceProfile:
        if origin not in self._profiles:
            self._profiles[origin] = ResilienceProfile(origin=origin)
        return self._profiles[origin]

    def tick(self, world: World, collapse_origins: list[str]) -> None:
        for f in world.map.all():
            o = f.pluis.origin
            p = self.get_or_create(o)
            p.update(collapsed=o in collapse_origins)

    def resilience(self, origin: str) -> float:
        return self._profiles.get(origin, ResilienceProfile(origin)).resilience_score

    def ranking(self) -> list[tuple[str, float]]:
        return sorted(
            [(o, p.resilience_score) for o, p in self._profiles.items()],
            key=lambda x: x[1], reverse=True
        )


# ── Combined Evolution Step ────────────────────────────────────────────────────

def evolve(f: Field,
           world: World,
           key_pair: PluisKeyPair,
           disturbance: float = 0.0,
           collapses_survived: int = 0) -> Field:
    """
    Apply all evolution mechanisms to a single Field.
    Order: Echo Mutation → Drift Evolution → Basin Morphing.
    """
    lineage = world.lineage(f.pluis.origin)

    # 1. Echo Mutation (only under disturbance)
    if abs(disturbance) > 0.1:
        f = echo_mutate(f, disturbance, key_pair)

    # 2. Drift Evolution
    if len(lineage) >= 2:
        f = drift_evolve(f, lineage, key_pair)

    # 3. Basin Morphing
    if collapses_survived > 0:
        f = basin_morph(f, collapses_survived, key_pair)

    return f
