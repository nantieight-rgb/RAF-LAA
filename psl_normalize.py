"""
RAF:LAA PSL Normalization Layer.

PSL validates and normalizes Fields before any operator or transmission.
Rule 5 now uses PluisToken.verify() instead of a regex string check.
"""

import math
import re
from dataclasses import dataclass

from .ast_nodes import Field, Basin, Drift, Curvature, Echo, Gravity
from .pluis_token import PluisKeyPair, verify
from .operators import _rebuild

_ECHO_VALID_RE       = re.compile(r'^(S\d+|[A-Za-z]|NullEcho)$')
_INCONSISTENCY_LIMIT = 2.0


class PSLRejection(Exception):
    pass


@dataclass
class PSLResult:
    field:         Field
    rules_applied: list[str]
    rejected:      bool
    meaning:       None = None


def psl_normalize(field: Field,
                  key_pair: PluisKeyPair,
                  last_pes: float = 0.0) -> PSLResult:
    """
    Normalize a Field through PSL rules R1-R6.

    Args:
        field:    Field to normalize.
        key_pair: PluisKeyPair for PluisToken verification.
        last_pes: Last known PES value held by the system.

    Raises PSLRejection on Rule 5 (bad PluisToken) or Rule 6 (PES reversal).
    """
    drift     = field.basin.drift
    curvature = drift.curvature.value
    gravity   = drift.gravity.value
    echo_sym  = drift.echo.symbol
    rules:    list[str] = []

    # R1: Curvature clamp
    if not (-1.0 <= curvature <= 1.0):
        curvature = max(-1.0, min(1.0, curvature))
        rules.append("R1:curvature_clamped")

    # R2: Gravity normalize (attractor = negative)
    if not (-1.0 <= gravity <= 0.0):
        gravity = max(-1.0, min(0.0, gravity))
        rules.append("R2:gravity_normalized")

    # R3: Echo validate
    if not _ECHO_VALID_RE.match(echo_sym):
        echo_sym = "NullEcho"
        rules.append("R3:echo_nulled")

    # R4: Drift consistency
    if _inconsistent(curvature, gravity):
        curvature = 0.0
        gravity   = -0.5
        rules.append("R4:drift_reconstructed")

    # R5: PluisToken verification
    if not verify(field, field.pluis, key_pair):
        raise PSLRejection(
            f"PluisToken verification failed for origin={field.pluis.origin[:20]}..."
        )

    # R6: PES time-reversal
    if field.pes_timestamp < last_pes:
        raise PSLRejection(
            f"PES reversal: field={field.pes_timestamp} < last={last_pes}"
        )

    # Rebuild with normalized values (PluisToken inherited)
    normalized = _rebuild(
        field, key_pair,
        curvature=curvature,
        echo_symbol=echo_sym,
        gravity=gravity,
        advance_pes=False,
    )

    return PSLResult(field=normalized, rules_applied=rules, rejected=False)


def _inconsistent(curvature: float, gravity: float) -> bool:
    if math.isnan(curvature) or math.isnan(gravity): return True
    if math.isinf(curvature) or math.isinf(gravity): return True
    return abs(curvature) + abs(gravity) > _INCONSISTENCY_LIMIT
