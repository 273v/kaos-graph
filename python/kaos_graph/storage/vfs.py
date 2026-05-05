"""VFS artifact storage for graphs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from kaos_graph.errors import KaosGraphError

if TYPE_CHECKING:
    from kaos_graph.graph import Graph


# A2-#7: graph names go directly into "graphs/{name}.json" VFS paths. Validate
# tightly to prevent traversal ("../"), namespace escape ("../../etc/passwd"),
# windows reserved-name surprises, and accidental NUL bytes.
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}$")
_RESERVED = frozenset({".", "..", ".active"})


def _validate_name(name: str) -> str:
    """Reject graph names that would escape the graphs/ namespace.

    Allowed: ASCII letters, digits, underscore, hyphen, dot. Leading dot,
    pure-dot, and leading hyphen are all rejected; max 128 chars.
    """
    if not isinstance(name, str):
        raise KaosGraphError(
            f"Graph name must be a string, got {type(name).__name__}. "
            "Use ASCII letters, digits, underscore, hyphen, or dot."
        )
    if not name:
        raise KaosGraphError("Graph name must be non-empty.")
    if name in _RESERVED or name.startswith("-") or name.startswith("."):
        raise KaosGraphError(
            f"Graph name {name!r} is reserved or starts with a reserved character. "
            "Use ASCII letters, digits, underscore, hyphen, or dot — must start with "
            "[A-Za-z0-9_]."
        )
    if "\x00" in name:
        raise KaosGraphError("Graph name must not contain NUL bytes.")
    if not _NAME_RE.match(name):
        raise KaosGraphError(
            f"Invalid graph name {name!r}. Allowed: ASCII letters, digits, "
            "underscore, hyphen, dot; max 128 chars; must start with [A-Za-z0-9_]. "
            "Got something with disallowed characters or length."
        )
    return name


def _validate_context(context: Any) -> Any:
    """Validate that context has runtime, VFS, and artifacts. Returns context."""
    if context is None or not hasattr(context, "runtime") or context.runtime is None:
        raise ValueError("save_to_vfs/load_from_vfs requires a KaosContext with a KaosRuntime")
    return context


async def save_to_vfs(
    graph: Graph,
    name: str,
    *,
    context: Any = None,
    description: str = "",
) -> str:
    """Save a graph as a VFS artifact. Returns the artifact URI.

    Requires kaos-core. Raises ImportError if not installed.

    Raises:
        KaosGraphError: if ``name`` would escape the ``graphs/`` namespace
            (audit A2-#7).
    """
    safe_name = _validate_name(name)
    ctx = _validate_context(context)

    json_data = graph.to_json()
    artifacts = ctx.runtime.artifacts
    vfs = ctx.runtime.vfs
    sid: str = ctx.session_id

    path = f"graphs/{safe_name}.json"
    await vfs.write(path, json_data.encode(), context_id=sid)

    manifest = await artifacts.create_from_path(
        path,
        context_id=sid,
        session_id=sid,
        name=safe_name,
        description=description or f"Graph: {graph.n_nodes} nodes, {graph.n_edges} edges",
        mime_type="application/json",
    )

    return manifest.uri


async def load_from_vfs(
    name: str,
    *,
    context: Any = None,
) -> Graph:
    """Load a graph from a VFS artifact.

    Requires kaos-core. Raises ImportError if not installed.

    Raises:
        KaosGraphError: if ``name`` would escape the ``graphs/`` namespace
            (audit A2-#7).
    """
    from kaos_graph.graph import Graph

    safe_name = _validate_name(name)
    ctx = _validate_context(context)

    vfs = ctx.runtime.vfs
    sid: str = ctx.session_id
    path = f"graphs/{safe_name}.json"
    data = await vfs.read(path, context_id=sid)
    return Graph.from_json(data.decode())
