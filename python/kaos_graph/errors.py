"""kaos-graph error types.

The base ``KaosGraphError`` is a plain ``Exception`` so that ``import
kaos_graph`` (and ``import kaos_graph.io``, ``import kaos_graph.rdf``,
``import kaos_graph.storage`` and the rest of the standalone Python surface)
work in environments that have not installed the ``[mcp]`` extra and
therefore lack ``kaos-core``. When kaos-core *is* installed, the same class
additionally inherits from ``KaosCoreError`` so ``except KaosCoreError`` blocks
in MCP-aware consumers continue to catch every kaos-graph error. Audit
finding A2-#2.
"""

from __future__ import annotations

__all__ = [
    "CycleError",
    "EdgeNotFoundError",
    "GraphSizeError",
    "InvalidFormatError",
    "KaosGraphError",
    "NodeNotFoundError",
    "PathTraversalError",
    "PickleStateError",
]


def _resolve_base() -> type[Exception]:
    """Return KaosCoreError when kaos-core is installed, plain Exception otherwise."""
    try:
        from kaos_core.exceptions import KaosCoreError  # type: ignore[import-not-found]

        return KaosCoreError
    except ImportError:
        return Exception


_KaosCoreError: type[Exception] = _resolve_base()


class KaosGraphError(_KaosCoreError):  # ty: ignore[unsupported-base]
    """Base exception for kaos-graph.

    Inherits from ``kaos_core.exceptions.KaosCoreError`` when available and
    from plain ``Exception`` otherwise (ty cannot statically resolve the
    runtime-conditional base; the ``ty: ignore`` comment is intentional).
    Either way, ``except Exception`` always works.
    """


class NodeNotFoundError(KaosGraphError, KeyError):
    """Raised when a node ID is not found in the graph."""


class EdgeNotFoundError(KaosGraphError, KeyError):
    """Raised when an edge is not found in the graph."""


class CycleError(KaosGraphError, ValueError):
    """Raised when a cycle is detected in an operation that requires a DAG."""


class InvalidFormatError(KaosGraphError, ValueError):
    """Raised when an input file format is invalid or unsupported."""


class GraphSizeError(KaosGraphError, ValueError):
    """Raised when an input or computation exceeds a configured cap.

    Carries the offending count and the cap so callers can surface a clear
    error message and operators can decide whether to raise the cap.
    """

    def __init__(self, kind: str, count: int, cap: int) -> None:
        super().__init__(
            f"kaos-graph {kind} cap exceeded: {count} > {cap}. "
            f"Raise via KAOS_GRAPH_MAX_{kind.upper()} or KaosGraphSettings.max_{kind} "
            f"if your workload genuinely requires it."
        )
        self.kind = kind
        self.count = count
        self.cap = cap


class PathTraversalError(KaosGraphError, ValueError):
    """Raised when a file path resolves outside the configured allowlist root."""

    def __init__(self, path: str, root: str | None) -> None:
        if root is None:
            msg = (
                f"Refusing to read '{path}': KaosGraphSettings.allowed_root is not "
                f"configured. Set KAOS_GRAPH_ALLOWED_ROOT or pass allowed_root in "
                f"_meta.kaos_config when calling kaos-graph-load-rdf."
            )
        else:
            msg = (
                f"Path '{path}' resolves outside the allowed root '{root}'. "
                f"Either move the file into the allowed root or extend "
                f"KAOS_GRAPH_ALLOWED_ROOT to cover it."
            )
        super().__init__(msg)
        self.path = path
        self.root = root


class PickleStateError(KaosGraphError, ValueError):
    """Raised when an unpickle operation rejects state (size, magic, version)."""
