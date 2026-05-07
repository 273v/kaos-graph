"""kaos-graph MCP tools.

Defines 17 MCP tools for graph operations across 5 domain modules. All
``kaos-core`` imports are lazy (inside ``register_graph_tools``) so that
``import kaos_graph.tools`` stays usable in standalone deployments without
kaos-core installed (audit A2-#2). At module-import time we only need
``json``, ``logging``, and ``typing``.

Tool counts per domain (audit-01 KG-004 split):

- :mod:`kaos_graph.tools._core`        — 5 tools (create, query, info, transform, validate-schema)
- :mod:`kaos_graph.tools._algorithms`  — 4 tools (algorithm, critical-path, find-patterns, stats)
- :mod:`kaos_graph.tools._rdf`         — 3 tools (load-rdf, load-rdf-string, sparql)
- :mod:`kaos_graph.tools._io`          — 4 tools (export, visualize, load-/export-adjacency)
- :mod:`kaos_graph.tools._programs`    — 1 tool  (trace-to-graph)
"""

from __future__ import annotations

from typing import Any, Protocol

from kaos_graph.tools._common import (
    _ALGORITHMS,
    _EXPORT_FORMATS,
    _MODULE,
    _VERSION,
    get_logger,
)

__all__ = [
    "_ALGORITHMS",
    "_EXPORT_FORMATS",
    "_MODULE",
    "_VERSION",
    "logger",
    "register_graph_tools",
]


# Audit A2-#2 regression: ``kaos_graph.tools.logger`` must exist on import so
# the standalone-import test in tests/security/test_audit_a2.py passes even
# when kaos-core is absent. ``get_logger()`` falls back to stdlib logging.
logger = get_logger()


class _RuntimeLike(Protocol):
    # Duck-typed: anything with a ``tools`` attribute that supports
    # ``.register_tool(tool)`` works. Declared as Any to keep MockRuntime /
    # KaosRuntime / partial fakes in tests assignable without casting.
    tools: Any


def register_graph_tools(runtime: _RuntimeLike) -> int:
    """Register all kaos-graph MCP tools with a KaosRuntime.

    Each domain module exposes a local ``register_<domain>_tools`` helper
    that owns the lazy kaos-core imports for that domain (audit-01 KG-004).
    The total count of registered tools is returned.

    Args:
        runtime: A ``KaosRuntime`` (or any object with a ``tools`` registry
            that exposes ``register_tool``).

    Returns:
        Total number of tools registered.

    Raises:
        ImportError: If kaos-core is not installed.
    """
    try:
        # Importing the base classes here verifies kaos-core is installed
        # before we delegate to the domain modules; each domain module
        # repeats the import locally so it can be tested in isolation.
        import kaos_core  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "kaos-core is required for MCP tool registration. Install with: pip install kaos-core"
        ) from e

    from kaos_graph.tools._algorithms import register_algorithm_tools
    from kaos_graph.tools._core import register_core_tools
    from kaos_graph.tools._io import register_io_tools
    from kaos_graph.tools._programs import register_program_tools
    from kaos_graph.tools._rdf import register_rdf_tools

    count = 0
    count += register_core_tools(runtime)
    count += register_algorithm_tools(runtime)
    count += register_rdf_tools(runtime)
    count += register_io_tools(runtime)
    count += register_program_tools(runtime)
    return count
