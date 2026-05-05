"""Bridge to kaos-content TabularDocument for SQL queries via kaos-tabular."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # kaos-content is the optional `[tabular]` extra (planned for v0.1.0a2
    # once kaos-content publishes to PyPI).
    from kaos_content.model.tabular import (  # ty: ignore[unresolved-import]
        TabularDocument,
    )

    from kaos_graph.graph import Graph

__all__ = ["to_tabular"]


def to_tabular(graph: Graph) -> tuple[TabularDocument, TabularDocument]:
    """Convert a graph to (nodes_table, edges_table) TabularDocuments.

    Returns two TabularDocument objects that can be registered with kaos-tabular
    for SQL queries.

    Requires kaos-content. Raises ImportError if not installed.
    """
    try:
        from kaos_content.model.tabular import (  # ty: ignore[unresolved-import]
            Column,
            ColumnType,
            Table,
            TabularDocument,
        )
    except ImportError as e:
        raise ImportError(
            "kaos-content is required for to_tabular(). Install with: pip install kaos-content"
        ) from e

    # Build nodes table
    node_ids = graph.node_ids()
    node_rows = []
    all_prop_keys: set[str] = set()

    for nid in node_ids:
        node = graph.node(nid)
        props = node.properties if node else {}
        all_prop_keys.update(props.keys())
        node_rows.append((nid, props))

    node_prop_keys = sorted(all_prop_keys)
    node_columns = (
        Column(name="id", column_type=ColumnType.TEXT),
        *(Column(name=k, column_type=ColumnType.TEXT) for k in node_prop_keys),
    )

    rows_data = []
    for nid, props in node_rows:
        row = (nid, *(str(props.get(k, "")) for k in node_prop_keys))
        rows_data.append(row)

    nodes_table = Table(
        name="nodes",
        columns=node_columns,
        rows=tuple(rows_data),
        row_count=len(rows_data),
    )

    # Build edges table
    edges = graph.edges()
    edge_prop_keys: set[str] = set()
    for edge in edges:
        edge_prop_keys.update(edge.properties.keys())
    edge_prop_keys_sorted = sorted(edge_prop_keys)

    edge_columns = (
        Column(name="source", column_type=ColumnType.TEXT),
        Column(name="target", column_type=ColumnType.TEXT),
        *(Column(name=k, column_type=ColumnType.TEXT) for k in edge_prop_keys_sorted),
    )

    edge_rows = []
    for edge in edges:
        row = (
            edge.source,
            edge.target,
            *(str(edge.properties.get(k, "")) for k in edge_prop_keys_sorted),
        )
        edge_rows.append(row)

    edges_table = Table(
        name="edges",
        columns=edge_columns,
        rows=tuple(edge_rows),
        row_count=len(edge_rows),
    )

    nodes_doc = TabularDocument(tables=(nodes_table,))
    edges_doc = TabularDocument(tables=(edges_table,))

    return nodes_doc, edges_doc
