"""
RAF:LAA Structural Operators.

All operators are pure functions: Field -> Field.
meaning is always None.
PluisToken is always preserved or properly inherited.
"""

import math
from .ast_nodes import Field, Basin, Drift, Curvature, Echo, Gravity
from .pluis_token import PluisKeyPair, inherit
from .pes import now_pes

COLLAPSE_THRESHOLD = 1.0
STABILIZE_TAU      = 0.01


def resonate(field: Field, key_pair: PluisKeyPair) -> Field:
    """
    Echo × Curvature interaction — modulates Drift.
    PES preserved (structural change only).
    PluisToken inherited with new hash.
    """
    drift = field.basin.drift
    echo_phase = _symbol_phase(drift.echo.symbol)
    new_curv = drift.curvature.value * math.cos(echo_phase)
    new_grav = drift.gravity.value * (1.0 + abs(math.sin(echo_phase)) * 0.5)
    return _rebuild(field, key_pair, curvature=new_curv,
                    echo_symbol=drift.echo.symbol, gravity=new_grav,
                    advance_pes=False)


def stabilize(field: Field, key_pair: PluisKeyPair) -> Field:
    """
    Normalize Basin around Gravity.
    PES preserved.
    """
    drift = field.basin.drift
    grav  = drift.gravity.value
    if abs(grav) < STABILIZE_TAU:
        return field
    damping  = 1.0 - min(abs(grav), 1.0)
    new_curv = drift.curvature.value * damping
    new_grav = -abs(grav)
    return _rebuild(field, key_pair, curvature=new_curv,
                    echo_symbol=drift.echo.symbol, gravity=new_grav,
                    advance_pes=False)


def collapse(field: Field, key_pair: PluisKeyPair) -> Field:
    """
    Reconstruct Basin when |Curvature| >= threshold.
    PES preserved (collapse is structural, not temporal).
    Echo (structural memory) survives.
    """
    drift = field.basin.drift
    if abs(drift.curvature.value) < COLLAPSE_THRESHOLD:
        return field
    return _rebuild(field, key_pair, curvature=0.0,
                    echo_symbol=drift.echo.symbol, gravity=-1.0,
                    advance_pes=False)


def rebirth(field: Field, key_pair: PluisKeyPair) -> Field:
    """
    Regenerate Field — same lineage, new phase.
    PES MUST advance.
    PluisToken origin inherited (same existence, new state).
    """
    drift = field.basin.drift
    seq   = (field.pes_seq + 1) if field.pes_seq is not None else None
    return _rebuild(field, key_pair, curvature=0.0,
                    echo_symbol=drift.echo.symbol, gravity=-0.5,
                    advance_pes=True, pes_seq=seq)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _symbol_phase(symbol: str) -> float:
    h = hash(symbol) & 0xFFFFFFFF
    return (h / 0xFFFFFFFF) * 2 * math.pi


def _rebuild(field: Field,
             key_pair: PluisKeyPair, *,
             curvature: float,
             echo_symbol: str,
             gravity: float,
             advance_pes: bool = False,
             pes_seq: int | None = None) -> Field:
    new_field = Field(
        basin=Basin(drift=Drift(
            curvature=Curvature(value=curvature),
            echo=Echo(symbol=echo_symbol),
            gravity=Gravity(value=gravity),
        )),
        pluis=field.pluis,           # temporary — will be replaced by inherit
        pes_timestamp=now_pes() if advance_pes else field.pes_timestamp,
        pes_seq=pes_seq if pes_seq is not None else field.pes_seq,
    )
    # inherit updates hash to match new_field's structure, preserving origin
    new_field.pluis = inherit(field.pluis, new_field, key_pair)
    return new_field
