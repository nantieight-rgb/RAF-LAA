"""
RAF:LAA PES — External Time Layer.

PES (Persistent External Sequence) is the monotonically increasing
time axis that gives Fields their temporal position.

Rules:
- PES only moves forward
- rebirth MUST advance PES (same existence, new phase)
- resonate / stabilize / collapse MAY preserve PES (structural change only)
"""

import time


def now_pes() -> float:
    """Current PES value — monotonic clock."""
    return time.monotonic()
