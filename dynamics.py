"""
RAF:LAA World Dynamics — Field-to-Field Interaction Physics.

Fields influence each other through three channels:
  - Echo   (phase): alignment drives resonance
  - Drift  (curvature): direction compatibility shapes momentum
  - Distance: attenuation by structural distance

resonance_strength ∈ [-1.0, 1.0]
  > 0  → constructive resonance (Curvature sync, Gravity deepens)
  < -0.5 → destructive interference (triggers collapse)

All functions are pure: (Field, ...) -> Field.
PluisToken is inherited on every structural change.
"""

from __future__ import annotations

import math
from typing import Optional

from .ast_nodes import Field, Basin, Drift, Curvature, Echo, Gravity
from .operators import collapse as op_collapse, _rebuild, _symbol_phase
from .pluis_token import PluisKeyPair, inherit
from .world import World, structural_distance


# ── Echo blending ─────────────────────────────────────────────────────────────

def _blend_echo(base: Echo, other: Echo, strength: float) -> Echo:
    """
    Blend two Echo symbols by phase interpolation.
    At strength=0, returns base unchanged.
    At strength=1, returns other.
    For intermediate values, returns the symbol whose phase
    is closer to the interpolated phase.
    """
    if strength <= 0.0:
        return base
    if strength >= 1.0:
        return other

    p_base  = _symbol_phase(base.symbol)
    p_other = _symbol_phase(other.symbol)

    # Circular interpolation (shortest arc)
    diff = p_other - p_base
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi

    target = (p_base + strength * diff) % (2 * math.pi)

    # Choose the symbol whose phase is closest to target
    if abs(_symbol_phase(base.symbol) - target) <= abs(_symbol_phase(other.symbol) - target):
        return base
    return other


# ── Resonance strength ────────────────────────────────────────────────────────

def resonance_strength(f1: Field, f2: Field) -> float:
    """
    Compute resonance strength between two Fields.
    Range: [-1.0, 1.0]
      > 0  → constructive
      ≈ 0  → neutral
      < 0  → destructive
    """
    dist        = structural_distance(f1, f2)
    attenuation = 1.0 / (1.0 + dist)

    # Phase difference normalized to [0, 1]  (0=same, 1=opposite)
    p1 = _symbol_phase(f1.basin.drift.echo.symbol)
    p2 = _symbol_phase(f2.basin.drift.echo.symbol)
    raw_diff = abs(p1 - p2) % (2 * math.pi)
    phase_diff = min(raw_diff, 2 * math.pi - raw_diff) / math.pi  # [0, 1]

    # Curvature direction difference normalized to [0, 1]
    c1 = f1.basin.drift.curvature.value
    c2 = f2.basin.drift.curvature.value
    drift_diff = min(abs(c1 - c2) / 2.0, 1.0)

    # Constructive component [0, 1]
    constructive = attenuation * (1.0 - phase_diff) * (1.0 - drift_diff)

    # Destructive component: near-opposite phase + near-opposite curvature
    destructive = attenuation * phase_diff * drift_diff

    return constructive - destructive


DESTRUCTIVE_THRESHOLD = -0.3
SYNC_RATE             = 0.1   # Curvature sync rate per tick
GRAVITY_DEEPEN        = 0.05  # Gravity deepening per tick (constructive)


# ── Pairwise interaction ──────────────────────────────────────────────────────

def interact(f1: Field, f2: Field,
             key_pair: PluisKeyPair) -> tuple[Field, Field]:
    """
    Apply one interaction step between two Fields.
    Returns (new_f1, new_f2) — pure, no mutation.
    """
    rs = resonance_strength(f1, f2)

    # Destructive interference → collapse both
    if rs < DESTRUCTIVE_THRESHOLD:
        return op_collapse(f1, key_pair), op_collapse(f2, key_pair)

    if abs(rs) < 1e-6:
        return f1, f2  # negligible interaction

    d1 = f1.basin.drift
    d2 = f2.basin.drift

    # Curvature synchronization
    c1 = d1.curvature.value + SYNC_RATE * rs * (d2.curvature.value - d1.curvature.value)
    c2 = d2.curvature.value + SYNC_RATE * rs * (d1.curvature.value - d2.curvature.value)
    c1 = max(-1.0, min(1.0, c1))
    c2 = max(-1.0, min(1.0, c2))

    # Gravity deepening (constructive only)
    g1 = d1.gravity.value - (GRAVITY_DEEPEN * rs if rs > 0 else 0)
    g2 = d2.gravity.value - (GRAVITY_DEEPEN * rs if rs > 0 else 0)
    g1 = max(-1.0, min(0.0, g1))
    g2 = max(-1.0, min(0.0, g2))

    # Echo phase blending
    e1 = _blend_echo(d1.echo, d2.echo, abs(rs) * SYNC_RATE)
    e2 = _blend_echo(d2.echo, d1.echo, abs(rs) * SYNC_RATE)

    new_f1 = _rebuild(f1, key_pair, curvature=c1, echo_symbol=e1.symbol, gravity=g1)
    new_f2 = _rebuild(f2, key_pair, curvature=c2, echo_symbol=e2.symbol, gravity=g2)
    return new_f1, new_f2


# ── World tick ────────────────────────────────────────────────────────────────

def world_tick(world: World, key_pair: PluisKeyPair) -> dict[str, float]:
    """
    Apply one full tick of dynamics across all Field pairs in the World.
    Returns a dict of resonance_strength values for each pair.
    Updates World in-place via world.apply().
    """
    fields  = world.map.all()
    origins = [f.pluis.origin for f in fields]
    current = {o: world.map.get(o) for o in origins}
    metrics: dict[str, float] = {}

    for i in range(len(origins)):
        for j in range(i + 1, len(origins)):
            o1, o2  = origins[i], origins[j]
            f1, f2  = current[o1], current[o2]
            rs      = resonance_strength(f1, f2)
            metrics[f"{o1[:8]}↔{o2[:8]}"] = round(rs, 4)

            new_f1, new_f2 = interact(f1, f2, key_pair)
            current[o1] = new_f1
            current[o2] = new_f2

    # Commit all changes
    for origin, new_field in current.items():
        old = world.map.get(origin)
        if old is not new_field:
            world.apply(old, new_field)

    return metrics
