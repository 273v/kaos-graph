"""Graphviz DOT format export."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

__all__ = ["to_dot"]


def _escape_dot(s: str) -> str:
    """Escape a string for use inside DOT double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def to_dot(
    graph: Graph,
    *,
    node_label: Callable[[str, dict], str] | None = None,
    edge_label: Callable[[str, str, dict], str] | None = None,
    graph_name: str = "G",
) -> str:
    """Export graph as Graphviz DOT string.

    Args:
        graph: The graph to export.
        node_label: Function ``(node_id, properties) -> label``. Default: use node ID.
        edge_label: Function ``(source, target, properties) -> label``. Default: none.
        graph_name: Name for the graph.

    Returns:
        A DOT language string.
    """
    directed = graph.is_directed
    keyword = "digraph" if directed else "graph"
    edge_op = "->" if directed else "--"

    lines: list[str] = [f'{keyword} "{_escape_dot(graph_name)}" {{']

    # Emit node definitions
    for nid in graph.node_ids():
        node = graph.node(nid)
        props = node.properties if node else {}
        label = node_label(nid, props) if node_label else nid
        lines.append(f'    "{_escape_dot(nid)}" [label="{_escape_dot(label)}"];')

    # Emit edges
    for edge in graph.edges():
        src_esc = _escape_dot(edge.source)
        tgt_esc = _escape_dot(edge.target)
        if edge_label:
            elabel = edge_label(edge.source, edge.target, edge.properties)
            if elabel:
                lines.append(
                    f'    "{src_esc}" {edge_op} "{tgt_esc}" [label="{_escape_dot(elabel)}"];'
                )
            else:
                lines.append(f'    "{src_esc}" {edge_op} "{tgt_esc}";')
        else:
            lines.append(f'    "{src_esc}" {edge_op} "{tgt_esc}";')

    lines.append("}")
    return "\n".join(lines) + "\n"
