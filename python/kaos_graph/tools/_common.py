"""Shared helpers for the kaos-graph MCP tool modules.

This module is imported by each domain submodule (``_core``, ``_algorithms``,
``_rdf``, ``_io``, ``_programs``). It owns the constants and helpers that
would otherwise duplicate across modules. All ``kaos-core`` imports are
performed lazily so ``import kaos_graph.tools`` does not pull kaos-core in
the standalone-library path (audit A2-#2).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaos_core.base.context import KaosContext
    from kaos_core.types.annotations import ToolAnnotations

__all__ = [
    "_ALGORITHMS",
    "_EXPORT_FORMATS",
    "_MODULE",
    "_VERSION",
    "get_logger",
    "graph_from_json",
    "readonly_annotations",
    "settings_for",
]

_MODULE = "kaos-graph"
_VERSION = "0.1.0a1"

# Algorithm names accepted by ``kaos-graph-algorithm``.
_ALGORITHMS = [
    "pagerank",
    "shortest_path",
    "bfs",
    "dfs",
    "topological_sort",
    "scc",
    "betweenness_centrality",
    "closeness_centrality",
    "eigenvector_centrality",
    "degree_centrality",
    "louvain",
    "label_propagation",
    "longest_path",
    "ancestors",
    "descendants",
]

# Export formats accepted by ``kaos-graph-export``.
_EXPORT_FORMATS = ["json", "mermaid", "dot", "turtle", "ntriples", "graphml", "gexf"]


def get_logger() -> logging.Logger:
    """Return a kaos-* logger when kaos-core is installed, else stdlib.

    Keeps the module import-clean for standalone consumers (audit A2-#2),
    while preserving session/trace correlation for MCP-aware deployments.
    """
    try:
        from kaos_core.logging import get_logger as _gl  # type: ignore[import-not-found]

        return _gl(__name__)
    except ImportError:
        return logging.getLogger(__name__)


def settings_for(context: KaosContext | None) -> Any:
    """Settings instance scoped to the current MCP context.

    Audit follow-up A2-#3: every MCP handler must thread the request's
    ``KaosGraphSettings`` through to ``Graph.from_json`` so caps reflect the
    configured / per-request overrides instead of the standalone defaults.
    """
    from kaos_graph.settings import KaosGraphSettings

    return KaosGraphSettings.from_context(context)


def graph_from_json(data: str, context: KaosContext | None = None) -> Any:
    """Parse a JSON graph definition into a Graph (capped via settings).

    Audit follow-up A2-#3: replaces the raw ``json.loads`` path that bypassed
    ``Graph.from_json`` and its byte/node/edge caps. Even the
    ``kaos-graph-create`` schema (top-level ``nodes``/``edges`` arrays) is
    canonicalized to the standard wire shape so a single capped codepath
    handles every MCP entry.
    """
    from kaos_graph.graph import Graph

    settings = settings_for(context)
    max_bytes = int(getattr(settings, "max_bytes", 64 * 1024 * 1024))
    if len(data) > max_bytes:
        raise ValueError(f"graph_json is {len(data)} bytes; max_bytes is {max_bytes}.")

    parsed = json.loads(data)
    canonical = {
        "directed": parsed.get("directed", True),
        "multi": parsed.get("multi", False),
        "name": parsed.get("name") or "",
        "nodes": [
            {"id": n["id"], "properties": {k: v for k, v in n.items() if k != "id"}}
            for n in parsed.get("nodes", [])
        ],
        "edges": [
            {
                "source": e["source"],
                "target": e["target"],
                "properties": {k: v for k, v in e.items() if k not in ("source", "target")},
            }
            for e in parsed.get("edges", [])
        ],
    }
    return Graph.from_json(json.dumps(canonical), settings=settings)


def readonly_annotations() -> ToolAnnotations:
    """Return shared ``ToolAnnotations`` for read-only, local-only tools.

    Imported lazily so the helper module stays usable without kaos-core in
    the standalone-library path. Every kaos-graph tool is read-only and
    operates on inline JSON / local files, so the same annotations apply
    across the whole tool surface.
    """
    from kaos_core.types.annotations import ToolAnnotations

    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
