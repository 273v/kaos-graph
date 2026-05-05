"""SPARQL query support via pyoxigraph.

Converts a kaos-graph Graph to an in-memory pyoxigraph Store, executes
SPARQL queries, and returns results in Python-native formats. pyoxigraph
is used because SPARQL evaluation is a complex operation where the Rust
boundary crossing overhead is negligible compared to query execution.

A2-followup-#3: query_sparql / query_sparql_ask take ``settings``-derived
caps for query bytes, evaluation timeout, and result rows. The MCP tool
boundary (kaos-graph-sparql) threads ``KaosGraphSettings.from_context``
through. Standalone Python callers get conservative defaults.
"""

from __future__ import annotations

import importlib
import signal
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaos_graph.graph import Graph

# Default predicate used when an edge has no "predicate" property.
_DEFAULT_PREDICATE = "http://kaos.273v.com/graph#relatedTo"

# Defaults applied when no settings instance is supplied. SPARQL is the
# heaviest operation kaos-graph exposes; conservative defaults that still
# cover legitimate analytical queries.
_DEFAULT_MAX_QUERY_BYTES = 64 * 1024  # 64 KiB query string
_DEFAULT_MAX_ROWS = 100_000
_DEFAULT_TIMEOUT_S = 30


@dataclass(slots=True, frozen=True)
class SparqlResult:
    """Result of a SPARQL SELECT query.

    Attributes:
        variables: The variable names from the query.
        rows: List of dicts mapping variable names to string values.
        truncated: True when the result was capped at ``max_rows``.
    """

    variables: list[str]
    rows: list[dict[str, str]]
    truncated: bool = False


class SparqlTimeoutError(TimeoutError):
    """Raised when SPARQL evaluation exceeds the configured timeout."""


def _require_pyoxigraph() -> Any:
    try:
        return importlib.import_module("pyoxigraph")
    except ImportError as e:
        raise ImportError(
            "pyoxigraph is required for SPARQL support. "
            "Install it with: pip install kaos-graph[rdf]"
        ) from e


def _resolve_caps(settings: Any) -> tuple[int, int, int]:
    """Pull (max_query_bytes, max_rows, timeout_s) from a settings-like object.

    Falls back to module-level defaults when the settings object is missing
    a field. ``settings`` can be ``None``.
    """
    if settings is None:
        return (_DEFAULT_MAX_QUERY_BYTES, _DEFAULT_MAX_ROWS, _DEFAULT_TIMEOUT_S)
    return (
        int(getattr(settings, "max_query_bytes", _DEFAULT_MAX_QUERY_BYTES)),
        int(getattr(settings, "max_rows", _DEFAULT_MAX_ROWS)),
        int(getattr(settings, "max_time_s", _DEFAULT_TIMEOUT_S)),
    )


@contextmanager
def _wall_clock_deadline(seconds: int) -> Iterator[None]:
    """Best-effort wall-clock cap on the enclosed block.

    Uses ``signal.SIGALRM`` on POSIX main threads (cheap, OS-enforced).
    Falls back to a no-op on Windows or non-main threads, where SIGALRM
    isn't available; in those cases the row-cap inside ``query_sparql``
    still bounds memory.
    """
    on_main_posix = (
        hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread()
    )
    if not on_main_posix or seconds <= 0:
        yield
        return

    def _on_alarm(signum: int, frame: Any) -> None:
        raise SparqlTimeoutError(
            f"SPARQL evaluation exceeded the configured timeout ({seconds}s). "
            "Raise KAOS_GRAPH_MAX_TIME_S if the query genuinely needs longer."
        )

    prior = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prior)


def _term_to_str(term: Any) -> str:
    """Convert a pyoxigraph term to a string representation."""
    pyoxigraph = _require_pyoxigraph()

    if isinstance(term, pyoxigraph.NamedNode):
        return term.value
    elif isinstance(term, pyoxigraph.BlankNode):
        return f"_:{term.value}"
    elif isinstance(term, pyoxigraph.Literal):
        return term.value
    elif term is None:
        return ""
    else:
        return str(term)


def _graph_to_store(graph: Graph) -> Any:
    """Convert a kaos-graph Graph to a pyoxigraph Store.

    Each edge becomes an RDF triple. The edge's ``predicate`` property
    (if present) is used as the predicate IRI; otherwise the default
    ``http://kaos.273v.com/graph#relatedTo`` is used. Node IDs starting
    with ``_:`` are treated as blank nodes.
    """
    pyoxigraph = _require_pyoxigraph()

    store = pyoxigraph.Store()

    for edge in graph.edges():
        pred_iri = edge.properties.get("predicate", _DEFAULT_PREDICATE)

        # Build subject
        if edge.source.startswith("_:"):
            subj = pyoxigraph.BlankNode(edge.source[2:])
        else:
            subj = pyoxigraph.NamedNode(edge.source)

        # Build predicate
        pred = pyoxigraph.NamedNode(pred_iri)

        # Build object
        if edge.target.startswith("_:"):
            obj = pyoxigraph.BlankNode(edge.target[2:])
        else:
            obj = pyoxigraph.NamedNode(edge.target)

        store.add(pyoxigraph.Quad(subj, pred, obj))

    return store


def query_sparql(graph: Graph, query: str, *, settings: Any = None) -> SparqlResult:
    """Execute a SPARQL SELECT query over a Graph.

    Converts the graph to an in-memory pyoxigraph Store, executes the
    query, and returns results as a :class:`SparqlResult`. Caps from
    ``settings`` (or module defaults) bound query size, result-row count,
    and wall-clock evaluation time (audit follow-up #3).

    Args:
        graph: The graph to query.
        query: A SPARQL SELECT query string.
        settings: Optional :class:`KaosGraphSettings` providing
            ``max_query_bytes`` / ``max_rows`` / ``max_time_s``.

    Returns:
        A SparqlResult with variable names, result rows, and a
        ``truncated`` flag indicating whether ``max_rows`` was reached.

    Raises:
        ImportError: If pyoxigraph is not installed.
        ValueError: If the query is invalid or exceeds ``max_query_bytes``.
        SparqlTimeoutError: If evaluation exceeds ``max_time_s``.
    """
    _require_pyoxigraph()
    max_query_bytes, max_rows, timeout_s = _resolve_caps(settings)

    if len(query) > max_query_bytes:
        raise ValueError(
            f"SPARQL query is {len(query)} bytes; max_query_bytes is "
            f"{max_query_bytes}. Raise KAOS_GRAPH_MAX_QUERY_BYTES if intended."
        )

    store = _graph_to_store(graph)

    with _wall_clock_deadline(timeout_s):
        try:
            results = store.query(query)
        except SyntaxError as e:
            raise ValueError(f"Invalid SPARQL query: {e}") from e

        # Handle SELECT queries (QuerySolutions)
        if hasattr(results, "variables"):
            variables = [v.value for v in results.variables]
            rows: list[dict[str, str]] = []
            truncated = False
            for row in results:
                if len(rows) >= max_rows:
                    truncated = True
                    break
                row_dict: dict[str, str] = {}
                for i, var in enumerate(variables):
                    row_dict[var] = _term_to_str(row[i])
                rows.append(row_dict)
            return SparqlResult(variables=variables, rows=rows, truncated=truncated)

        # Handle ASK queries (QueryBoolean)
        raise ValueError(
            "Only SPARQL SELECT queries are supported. Use query_sparql_ask() for ASK queries."
        )


def query_sparql_ask(graph: Graph, query: str, *, settings: Any = None) -> bool:
    """Execute a SPARQL ASK query over a Graph.

    Args:
        graph: The graph to query.
        query: A SPARQL ASK query string.
        settings: Optional :class:`KaosGraphSettings` providing
            ``max_query_bytes`` and ``max_time_s``.

    Returns:
        True if the ASK pattern matches, False otherwise.

    Raises:
        ImportError: If pyoxigraph is not installed.
        ValueError: If the query is invalid or exceeds ``max_query_bytes``.
        SparqlTimeoutError: If evaluation exceeds ``max_time_s``.
    """
    _require_pyoxigraph()
    max_query_bytes, _max_rows, timeout_s = _resolve_caps(settings)

    if len(query) > max_query_bytes:
        raise ValueError(
            f"SPARQL ASK query is {len(query)} bytes; max_query_bytes is "
            f"{max_query_bytes}. Raise KAOS_GRAPH_MAX_QUERY_BYTES if intended."
        )

    store = _graph_to_store(graph)

    with _wall_clock_deadline(timeout_s):
        try:
            result = store.query(query)
        except SyntaxError as e:
            raise ValueError(f"Invalid SPARQL query: {e}") from e

        return bool(result)


__all__ = [
    "SparqlResult",
    "SparqlTimeoutError",
    "query_sparql",
    "query_sparql_ask",
]
