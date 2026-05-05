"""Convert kaos-llm-core Programs and ExecutionTraces to analyzable Graphs.

- ``program_to_graph()`` — static structure (containment tree from named_calls)
- ``trace_to_graph()`` — runtime data-flow graph from an ExecutionTrace,
  with timing/cost on nodes for ``critical_path()`` analysis

Requires kaos-llm-core; raises ImportError if not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

__all__ = ["program_to_graph", "trace_to_graph"]


def program_to_graph(program: object) -> Graph:
    """Convert a kaos-llm-core Program to a Graph for visualization and analysis.

    Each Call or sub-Program in the program becomes a node. Containment
    relationships become directed edges with ``type="contains"``.
    The resulting graph is a DAG rooted at a synthetic ``__program__`` node.

    Args:
        program: A ``kaos_llm_core.programs.base.Program`` instance.

    Returns:
        A directed ``Graph`` representing the program's Call tree.

    Raises:
        ImportError: If kaos-llm-core is not installed.
        TypeError: If *program* is not a Program instance.
    """
    from kaos_graph.graph import Graph

    try:
        from kaos_llm_core.programs.base import Program  # ty: ignore[unresolved-import]
    except ImportError as e:
        raise ImportError(
            "kaos-llm-core is required for program_to_graph(). "
            "Install with: pip install kaos-llm-core"
        ) from e

    if not isinstance(program, Program):
        raise TypeError(f"Expected a Program, got {type(program).__name__}")

    g = Graph(directed=True, name=program.__class__.__name__)

    # Add program root node
    g.add_node("__program__", type="program", class_name=type(program).__name__)

    def _walk(parent_id: str, obj: object, prefix: str = "") -> None:
        """Recursively walk a Program's named_calls tree.

        Discovers all Call and sub-Program children at arbitrary depth.
        Data-flow edges (outputs of one call feeding inputs of another)
        are not captured here -- they would require runtime trace
        inspection rather than static structure analysis.
        """
        if not isinstance(obj, Program):
            return
        named = obj.named_calls()
        for name, child in named.items():
            node_id = f"{prefix}{name}" if prefix else name
            node_type = "program" if isinstance(child, Program) else "call"
            if not g.has_node(node_id):
                g.add_node(node_id, type=node_type, class_name=type(child).__name__)
            if not g.has_edge(parent_id, node_id):
                g.add_edge(parent_id, node_id, type="contains")
            # Recurse into sub-programs
            if isinstance(child, Program):
                _walk(node_id, child, prefix=f"{node_id}.")

    _walk("__program__", program)

    return g


def trace_to_graph(trace: object) -> Graph:
    """Convert a kaos-llm-core ExecutionTrace to a data-flow Graph.

    Each trace node becomes a graph node with timing and cost properties.
    Sequential children are connected by ``type="data_flow"`` edges,
    representing the execution order (child N's outputs feed child N+1).

    The resulting DAG supports ``critical_path()`` analysis via the
    ``latency_ms`` edge/node property.

    Args:
        trace: A ``kaos_llm_core.observability.traces.ExecutionTrace`` instance.

    Returns:
        A directed ``Graph`` with data-flow edges and timing properties.

    Raises:
        ImportError: If kaos-llm-core is not installed.
        TypeError: If *trace* is not an ExecutionTrace instance.
    """
    from kaos_graph.graph import Graph

    try:
        from kaos_llm_core.observability.traces import (  # ty: ignore[unresolved-import]
            ExecutionTrace,
        )
    except ImportError as e:
        raise ImportError(
            "kaos-llm-core is required for trace_to_graph(). "
            "Install with: pip install kaos-llm-core"
        ) from e

    if not isinstance(trace, ExecutionTrace):
        raise TypeError(f"Expected an ExecutionTrace, got {type(trace).__name__}")

    g = Graph(directed=True, name=trace.call_name or "trace")

    def _add_trace(t: ExecutionTrace, prefix: str = "") -> str:
        """Add a trace node and its children. Returns the node ID."""
        node_id = f"{prefix}{t.call_name}" if prefix else (t.call_name or t.trace_id)
        # Avoid duplicate node IDs by appending trace_id suffix
        if g.has_node(node_id):
            node_id = f"{node_id}_{t.trace_id[:8]}"

        g.add_node(
            node_id,
            type="call",
            call_name=t.call_name,
            model=t.model,
            latency_ms=t.latency_ms,
            cost_usd=t.cost_usd,
            input_tokens=t.input_tokens,
            output_tokens=t.output_tokens,
            total_tokens=t.total_tokens,
        )

        # Add children and connect them sequentially (data-flow edges)
        child_ids: list[str] = []
        for child in t.children:
            child_prefix = f"{node_id}." if node_id else ""
            child_id = _add_trace(child, prefix=child_prefix)
            child_ids.append(child_id)

        # Containment: parent → each child
        for cid in child_ids:
            g.add_edge(node_id, cid, type="contains")

        # Data-flow: sequential children connected in order
        for i in range(len(child_ids) - 1):
            g.add_edge(child_ids[i], child_ids[i + 1], type="data_flow")

        return node_id

    _add_trace(trace)
    return g
