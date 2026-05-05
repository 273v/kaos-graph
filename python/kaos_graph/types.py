"""Typed result classes for kaos-graph algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Node:
    """A graph node with ID and properties."""

    id: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access to properties for backward compatibility."""
        return self.properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.properties

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)


@dataclass(slots=True)
class Edge:
    """A graph edge with source, target, and properties."""

    source: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access to properties for backward compatibility."""
        return self.properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.properties

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)


@dataclass(slots=True, frozen=True)
class PathResult:
    """Result of a shortest-path computation."""

    cost: float
    path: list[str]


@dataclass(slots=True, frozen=True)
class LongestPathResult:
    """Result of a longest-path computation on a DAG."""

    length: int
    path: list[str]


@dataclass(slots=True, frozen=True)
class NodeRank:
    """A node with its centrality/rank score."""

    node_id: str
    score: float


@dataclass(slots=True, frozen=True)
class BfsNode:
    """A node with its BFS depth."""

    node_id: str
    depth: int


@dataclass(slots=True, frozen=True)
class DfsEvent:
    """A DFS traversal event."""

    node_id: str
    event: str  # "enter" or "exit"


@dataclass(slots=True, frozen=True)
class Triple:
    """An RDF-style (subject, predicate, object) triple."""

    subject: str
    predicate: str
    object: str


__all__ = [
    "BfsNode",
    "DfsEvent",
    "Edge",
    "LongestPathResult",
    "Node",
    "NodeRank",
    "PathResult",
    "Triple",
]
