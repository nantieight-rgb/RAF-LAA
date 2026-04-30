"""
RAF:LAA World Layer — FieldMap + FieldGraph.

FieldMap  = static snapshot  (RAM — who exists now)
FieldGraph = dynamic history  (journal — how existence changed)

Key invariant:
  origin == existence identity
  - same origin → same existence, time transition (node update)
  - new  origin → new  existence (new node + edge from parent)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .ast_nodes import Field


# ── FieldMap ──────────────────────────────────────────────────────────────────

@dataclass
class FieldMap:
    """
    Static snapshot of currently existing Fields.
    Key = PluisToken.origin (existence identity).
    """
    _fields: dict[str, Field] = field(default_factory=dict)

    def add(self, f: Field) -> None:
        """Register a new existence."""
        self._fields[f.pluis.origin] = f

    def update(self, f: Field) -> None:
        """Update an existing existence (same origin, new state)."""
        if f.pluis.origin not in self._fields:
            raise KeyError(f"Unknown origin: {f.pluis.origin[:20]}...")
        self._fields[f.pluis.origin] = f

    def get(self, origin: str) -> Optional[Field]:
        return self._fields.get(origin)

    def remove(self, origin: str) -> None:
        self._fields.pop(origin, None)

    def all(self) -> list[Field]:
        return list(self._fields.values())

    def __len__(self) -> int:
        return len(self._fields)

    def __contains__(self, origin: str) -> bool:
        return origin in self._fields


# ── FieldGraph ────────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    origin:    str
    field:     Field            # latest state of this existence
    history:   list[Field]      # all previous states (oldest first)


@dataclass
class GraphEdge:
    parent_origin: str          # where this existence was born from
    child_origin:  str          # the new existence
    pes_at_split:  float        # PES when the split happened


@dataclass
class FieldGraph:
    """
    Dynamic transition structure.
    Tracks lineage, rebirth, and splits across time.
    """
    _nodes: dict[str, GraphNode] = field(default_factory=dict)
    _edges: list[GraphEdge]      = field(default_factory=list)

    def register(self, f: Field) -> None:
        """Register a new existence (origin not yet in graph)."""
        self._nodes[f.pluis.origin] = GraphNode(
            origin=f.pluis.origin,
            field=f,
            history=[],
        )

    def transition(self, f: Field) -> None:
        """
        Record a time transition for an existing origin.
        Used by resonate / stabilize / collapse / rebirth.
        """
        node = self._nodes.get(f.pluis.origin)
        if node is None:
            raise KeyError(f"Unknown origin: {f.pluis.origin[:20]}...")
        node.history.append(node.field)
        node.field = f

    def split(self, parent: Field, child: Field) -> None:
        """
        Record a split: parent existence spawned a new existence.
        Used when a genuinely new origin is created.
        """
        self.register(child)
        self._edges.append(GraphEdge(
            parent_origin=parent.pluis.origin,
            child_origin=child.pluis.origin,
            pes_at_split=child.pes_timestamp,
        ))

    def lineage(self, origin: str) -> list[Field]:
        """Full history of a single existence (oldest → newest)."""
        node = self._nodes.get(origin)
        if node is None:
            return []
        return node.history + [node.field]

    def children(self, origin: str) -> list[str]:
        """Origins that were spawned from this existence."""
        return [e.child_origin for e in self._edges
                if e.parent_origin == origin]

    def ancestors(self, origin: str) -> list[str]:
        """Origins that this existence was spawned from (walk upward)."""
        result = []
        current = origin
        while True:
            parents = [e.parent_origin for e in self._edges
                       if e.child_origin == current]
            if not parents:
                break
            current = parents[0]
            result.append(current)
        return result

    def node(self, origin: str) -> Optional[GraphNode]:
        return self._nodes.get(origin)

    def all_nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def all_edges(self) -> list[GraphEdge]:
        return list(self._edges)

    def __len__(self) -> int:
        return len(self._nodes)


# ── Structural distance ───────────────────────────────────────────────────────

def structural_distance(a: Field, b: Field) -> float:
    """
    Distance between two Fields in structural space.
    Based on Curvature, Gravity, and Echo phase.
    """
    da = a.basin.drift
    db = b.basin.drift

    d_curv  = (da.curvature.value - db.curvature.value) ** 2
    d_grav  = (da.gravity.value   - db.gravity.value)   ** 2
    d_echo  = (_symbol_phase(da.echo.symbol) -
               _symbol_phase(db.echo.symbol)) ** 2

    return math.sqrt(d_curv + d_grav + d_echo)


def _symbol_phase(symbol: str) -> float:
    h = hash(symbol) & 0xFFFFFFFF
    return (h / 0xFFFFFFFF) * 2 * math.pi


# ── World — convenience wrapper ───────────────────────────────────────────────

class World:
    """
    Combines FieldMap (now) + FieldGraph (history) into a single interface.
    This is the BandOS World Layer.
    """

    def __init__(self):
        self.map   = FieldMap()
        self.graph = FieldGraph()

    def create(self, f: Field) -> None:
        """Register a newly issued Field."""
        self.map.add(f)
        self.graph.register(f)

    def apply(self, old: Field, new: Field) -> None:
        """
        Apply an operator result (resonate/stabilize/collapse/rebirth).
        Same origin → time transition.
        """
        self.map.update(new)
        self.graph.transition(new)

    def spawn(self, parent: Field, child: Field) -> None:
        """
        A new existence spawned from parent (different origin).
        """
        self.map.add(child)
        self.graph.split(parent, child)

    def distance(self, origin_a: str, origin_b: str) -> Optional[float]:
        a = self.map.get(origin_a)
        b = self.map.get(origin_b)
        if a is None or b is None:
            return None
        return structural_distance(a, b)

    def lineage(self, origin: str) -> list[Field]:
        return self.graph.lineage(origin)

    def __len__(self) -> int:
        return len(self.map)
