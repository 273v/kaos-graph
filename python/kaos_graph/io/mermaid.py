"""Mermaid diagram export."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

__all__ = ["to_mermaid"]

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_id(node_id: str) -> str:
    """Sanitize a node ID for Mermaid compatibility.

    Replaces non-alphanumeric characters with ``_`` and prefixes with ``n_``
    if the result starts with a digit.
    """
    safe = _SANITIZE_RE.sub("_", node_id)
    if safe and safe[0].isdigit():
        safe = f"n_{safe}"
    # Ensure non-empty
    if not safe:
        safe = "n_empty"
    return safe


def _escape_mermaid_label(label: str) -> str:
    """Escape characters that are special inside Mermaid quoted labels."""
    return label.replace("\\", "\\\\").replace('"', "#quot;")


def to_mermaid(
    graph: Graph,
    *,
    node_label: Callable[[str, dict], str] | None = None,
    edge_label: Callable[[str, str, dict], str] | None = None,
    max_nodes: int = 50,
    direction: str = "TB",
) -> str:
    """Export graph as a Mermaid flowchart string.

    Args:
        graph: The graph to export.
        node_label: Function ``(node_id, properties) -> label``. Default: use node ID.
        edge_label: Function ``(source, target, properties) -> label``. Default: empty.
        max_nodes: Maximum nodes to render. Truncates with a note if exceeded.
        direction: Flow direction: ``TB``, ``BT``, ``LR``, ``RL``.

    Returns:
        A Mermaid flowchart string.
    """
    lines: list[str] = [f"flowchart {direction}"]

    all_node_ids = graph.node_ids()
    truncated = len(all_node_ids) > max_nodes
    visible_ids = set(all_node_ids[:max_nodes])

    # Emit node definitions
    for nid in all_node_ids[:max_nodes]:
        node = graph.node(nid)
        props = node.properties if node else {}
        label = node_label(nid, props) if node_label else nid
        safe_id = _sanitize_id(nid)
        escaped_label = _escape_mermaid_label(label)
        lines.append(f'    {safe_id}["{escaped_label}"]')

    # Emit edges (only between visible nodes)
    for edge in graph.edges():
        if edge.source not in visible_ids or edge.target not in visible_ids:
            continue
        safe_src = _sanitize_id(edge.source)
        safe_tgt = _sanitize_id(edge.target)
        if edge_label:
            elabel = edge_label(edge.source, edge.target, edge.properties)
            if elabel:
                escaped = _escape_mermaid_label(elabel)
                lines.append(f'    {safe_src} -->|"{escaped}"| {safe_tgt}')
            else:
                lines.append(f"    {safe_src} --> {safe_tgt}")
        else:
            lines.append(f"    {safe_src} --> {safe_tgt}")

    # Truncation note
    if truncated:
        omitted = len(all_node_ids) - max_nodes
        lines.append(f'    truncated_note["... {omitted} more nodes omitted"]')
        lines.append("    style truncated_note fill:#fff3cd,stroke:#ffc107")

    return "\n".join(lines) + "\n"
