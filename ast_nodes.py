"""
RAF:LAA AST nodes.

Grammar:
  <field>     ::= "Field" "{" <basin> <signature> "}"
  <basin>     ::= "Basin" "{" <drift> "}"
  <drift>     ::= "Drift" "{" <curvature> <echo> <gravity> "}"
  <curvature> ::= "Curvature" ":" <number>
  <echo>      ::= "Echo" ":" <symbol>
  <gravity>   ::= "Gravity" ":" <number>
  <signature> ::= "Signature" ":" <pluis_token_string>
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pluis_token import PluisToken


@dataclass
class Curvature:
    value: float


@dataclass
class Echo:
    symbol: str


@dataclass
class Gravity:
    value: float


@dataclass
class Drift:
    curvature: Curvature
    echo:      Echo
    gravity:   Gravity


@dataclass
class Basin:
    drift: Drift


@dataclass
class Field:
    basin:         Basin
    pluis:         "PluisToken"      # existence proof (replaces Signature)
    pes_timestamp: float             # external time axis — monotonically increasing
    pes_seq:       Optional[int] = None

    def meaning(self):
        return None   # always None — RAF:LAA carries no meaning
