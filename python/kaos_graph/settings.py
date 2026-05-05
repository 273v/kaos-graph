"""kaos-graph module settings.

Uses ``ModuleSettings`` from kaos-core for typed, environment-aware configuration.
Resolution order:
explicit overrides > KaosContext._config > KAOS_GRAPH_* env vars > .env > defaults.

The settings module is the single source of truth for the safety caps that
gate untrusted-input parsing and unbounded-compute algorithms (audit findings
A2-#1, #3, #4, #5). Importing this module requires kaos-core; standalone
``import kaos_graph`` does not pull this in.
"""

from __future__ import annotations

from kaos_core.config import ModuleSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict

__all__ = ["KaosGraphSettings"]


# Default caps. Conservative for v0.1; downstream consumers raise via env var
# or KaosContext._config when they need more headroom.
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB
_DEFAULT_MAX_NODES = 1_000_000  # 1M nodes
_DEFAULT_MAX_EDGES = 10_000_000  # 10M edges
_DEFAULT_MAX_TRIPLES = 10_000_000  # RDF triple cap
_DEFAULT_MAX_SIMPLE_PATHS = 10_000  # all_simple_paths result cap
_DEFAULT_MAX_CLIQUES = 10_000  # maximal_cliques result cap
_DEFAULT_MAX_DEPTH = 32  # default cutoff for path enumeration
_DEFAULT_MAX_PICKLE_BYTES = 64 * 1024 * 1024  # 64 MiB
_DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB HTTP request body
_DEFAULT_HTTP_HOST = "127.0.0.1"

# SPARQL caps (audit follow-up #3).
_DEFAULT_MAX_QUERY_BYTES = 64 * 1024  # 64 KiB SPARQL query string
_DEFAULT_MAX_ROWS = 100_000
_DEFAULT_MAX_TIME_S = 30  # SPARQL wall-clock cap (seconds)


class KaosGraphSettings(ModuleSettings):
    """Settings for kaos-graph module.

    The default values are chosen to be reasonable for in-process scientific
    use; production deployments that expose ``kaos-graph-serve --http`` should
    review and tighten these (especially ``allowed_root``, ``max_bytes``, and
    the algorithm caps).
    """

    # Filesystem allowlist: when set, file-loading tools (e.g. kaos-graph-load-rdf)
    # restrict reads to paths under this directory. Resolved with strict=True
    # before the read so symlinks must point inside the allowlist too. Default
    # ``None`` means "no allowlist" — file loaders refuse to read in that case
    # unless the call originates from in-process code that bypasses the tool layer.
    allowed_root: str | None = None

    # Compute caps (apply at parse / load / algorithm boundaries).
    max_bytes: int = Field(default=_DEFAULT_MAX_BYTES, ge=0)
    max_nodes: int = Field(default=_DEFAULT_MAX_NODES, ge=0)
    max_edges: int = Field(default=_DEFAULT_MAX_EDGES, ge=0)
    max_triples: int = Field(default=_DEFAULT_MAX_TRIPLES, ge=0)
    max_simple_paths: int = Field(default=_DEFAULT_MAX_SIMPLE_PATHS, ge=0)
    max_cliques: int = Field(default=_DEFAULT_MAX_CLIQUES, ge=0)
    max_depth: int = Field(default=_DEFAULT_MAX_DEPTH, ge=1)

    # Pickle / serde caps.
    max_pickle_bytes: int = Field(default=_DEFAULT_MAX_PICKLE_BYTES, ge=0)

    # HTTP server (kaos-graph-serve --http).
    http_host: str = _DEFAULT_HTTP_HOST
    http_max_body_bytes: int = Field(default=_DEFAULT_MAX_BODY_BYTES, ge=0)
    http_bearer_token: str | None = None
    http_cors_origin: str | None = None

    # SPARQL caps (audit follow-up #3). Apply when [rdf] extra is installed
    # and the kaos-graph-sparql tool is invoked.
    max_query_bytes: int = Field(default=_DEFAULT_MAX_QUERY_BYTES, ge=0)
    max_rows: int = Field(default=_DEFAULT_MAX_ROWS, ge=0)
    max_time_s: int = Field(default=_DEFAULT_MAX_TIME_S, ge=0)

    model_config = SettingsConfigDict(
        env_prefix="KAOS_GRAPH_",
        env_file=".env",
        extra="ignore",
    )
