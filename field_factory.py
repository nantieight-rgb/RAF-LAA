"""
RAF:LAA Field Factory.

create_field() is the canonical way to produce a Field with a valid PluisToken.
The parser uses _parse_to_field() for loading existing serialized Fields.
"""
from __future__ import annotations

import json
from .ast_nodes import Field, Basin, Drift, Curvature, Echo, Gravity
from .pluis_token import PluisToken, PluisKeyPair, issue, inherit
from .pes import now_pes


def create_field(basin: Basin,
                 key_pair: PluisKeyPair,
                 pes_timestamp: float | None = None,
                 pes_seq: int | None = None,
                 creator: str = "system") -> Field:
    """
    Issue a new Field with a fresh PluisToken.
    This is the canonical entry point for Field creation.
    """
    pes = pes_timestamp if pes_timestamp is not None else now_pes()
    # Temporary Field to compute the initial hash
    tmp = Field(basin=basin, pluis=None, pes_timestamp=pes, pes_seq=pes_seq)  # type: ignore
    token = issue(tmp, key_pair, creator=creator)
    return Field(basin=basin, pluis=token, pes_timestamp=pes, pes_seq=pes_seq)


# ── Serialization ─────────────────────────────────────────────────────────────

def _basin_to_dict(basin: Basin) -> dict:
    d = basin.drift
    return {
        "curvature": d.curvature.value,
        "echo":      d.echo.symbol,
        "gravity":   d.gravity.value,
    }


def _dict_to_basin(obj: dict) -> Basin:
    return Basin(drift=Drift(
        curvature=Curvature(value=float(obj["curvature"])),
        echo=Echo(symbol=obj["echo"]),
        gravity=Gravity(value=float(obj["gravity"])),
    ))


def field_to_string(field: Field) -> str:
    return json.dumps({
        "basin": _basin_to_dict(field.basin),
        "pluis": field.pluis.to_string(),
        "pes":   field.pes_timestamp,
        "seq":   field.pes_seq,
    }, separators=(",", ":"))


def field_from_string(s: str) -> Field:
    obj = json.loads(s)
    return Field(
        basin=_dict_to_basin(obj["basin"]),
        pluis=PluisToken.from_string(obj["pluis"]),
        pes_timestamp=float(obj["pes"]),
        pes_seq=obj.get("seq"),
    )
