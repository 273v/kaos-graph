# Changelog

All notable changes to `kaos-graph` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a1] — 2026-05-05

### Security

Pre-release audit pass A2 (14 findings, all fixed with regression tests):

- **A2-#1 (HIGH) — RDF loader path traversal closed.** `kaos-graph-load-rdf`
  no longer accepts arbitrary local paths. File reads require an
  ``allowed_root`` configured via ``KAOS_GRAPH_ALLOWED_ROOT`` (or
  ``KaosGraphSettings.allowed_root``); paths are resolved with
  ``strict=True`` and verified ``is_relative_to(root)`` to defeat both
  TOCTOU symlink-swap and ``..``-escape. The pre-call ``Path.exists()``
  probe is gone. New ``PathTraversalError`` exception type.
- **A2-#2 (HIGH) — `kaos-core` decoupled from standalone import path.**
  ``import kaos_graph`` (and ``.io``, ``.rdf``, ``.algorithms``,
  ``.storage``) now works without ``kaos-core`` installed.
  ``KaosGraphError`` falls back to plain ``Exception`` when kaos-core is
  absent and inherits from ``KaosCoreError`` when present.
  ``kaos_graph.tools`` no longer imports ``kaos_core.logging`` at
  module top.
- **A2-#3 (HIGH) — bounded compute on every user input.** ``Graph.from_json``,
  RDF parsing, ``all_simple_paths``, and ``maximal_cliques`` now enforce
  ``max_bytes`` / ``max_nodes`` / ``max_edges`` / ``max_triples`` /
  ``max_depth`` / ``max_paths`` / ``max_cliques`` caps configured via
  ``KaosGraphSettings`` (env-var prefix ``KAOS_GRAPH_``). PyO3 boundary
  requires explicit caps; pure-Rust callers can still pass
  ``usize::MAX`` for legacy unbounded behavior.
- **A2-#4 (HIGH) — pickle hardening.** ``PyGraph.__setstate__`` now
  validates a 4-byte magic header (``b"KGR1"``), enforces a 64 MiB hard
  size cap, and version-gates the format. Old pickles fail with a clear
  error rather than silently expanding.
- **A2-#5 (HIGH) — RDF/XML silent fallback removed.** ``detect_format``
  returns ``Option<RdfFormat>`` and refuses unknown extensions; callers
  must pass an explicit ``format=`` (turtle/ntriples/rdfxml/nquads/trig)
  for non-canonical paths.
- **A2-#6 (MED) — `defusedxml` for GraphML/GEXF.** ``from_graphml`` and
  ``from_gexf`` now parse via ``defusedxml.ElementTree.fromstring``
  (refuses XXE / billion-laughs / external entities) plus a 32 MiB
  byte cap.
- **A2-#7 (MED) — VFS graph names validated.** ``save_to_vfs`` /
  ``load_from_vfs`` reject names that escape the ``graphs/`` namespace
  (regex ``[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}``; rejects ``.``, ``..``,
  ``.active``, leading dot or hyphen, NUL bytes, slashes).
- **A2-#8 (MED) — RDF parallel-edge handling fixed.** RDF loaders now
  build a multi-graph (``Graph::new_multi(true, true)``) so distinct
  predicates between the same subject and object coexist as parallel
  edges instead of being silently coalesced. ``add_edge`` errors are
  propagated rather than swallowed via ``.ok()``.
- **A2-#9 (MED) — dependency clean-up.** ``bincode 1.3.3`` removed
  (RUSTSEC-2025-0141 unmaintained, was an unreferenced direct dep).
  Added ``deny.toml`` enforcing the platform license allowlist + ban on
  ``bincode<2.0.0``. Bumped ``cryptography``, ``pytest``, and
  ``python-multipart`` to known-safe versions in the dev group.
- **A2-#10 (MED) — sdist hygiene.** ``.gitignore`` excludes ``.kaos-vfs/``,
  ``target/``, ``__pycache__/``, and other runtime artifacts.
  ``[tool.maturin].exclude`` strips the same paths from sdist + wheel.
- **A2-#11 (MED) — `Graph.nodes(**filter)` short-circuit.** Empty
  intersection now exits the filter loop early, preventing O(N·k) scans
  when an early filter rules everything out.
- **A2-#12 (MED) — `kaos-graph-serve --http` gated to loopback.** Refuses
  to bind non-loopback hosts unless ``--allow-remote`` is explicitly
  passed alongside a bearer token; ``--allow-remote`` is currently
  reserved for a future release because the current ``kaos-mcp``
  transport does not enforce auth.
- **A2-#13 (MED) — `critical_path` typed error.** Non-numeric weight
  property raises ``KaosGraphError`` with a clear message instead of a
  generic ``ValueError`` from inside the DP loop.
- **A2-#14a (LOW) — `kaos_graph.rdf.__all__` conditional.** SPARQL
  symbols (``query_sparql``, ``query_sparql_ask``, ``SparqlResult``) are
  added to ``__all__`` only when ``pyoxigraph`` is importable.
- **A2-#14b/c (LOW) — `GraphJson` strict fields + pickle magic.**
  ``#[serde(deny_unknown_fields)]`` on ``GraphJson``, ``NodeJson``,
  ``EdgeJson`` rejects payload pollution. Pickle format adds the magic
  header from #4.

Follow-up audit pass (post-A2 review, 7 findings):

- **#1 (RDF library no longer refuses without allowed_root) — DELIBERATE.**
  Audit A2-#1 was scoped to the MCP-tool boundary, not the in-process
  library API. ``load_rdf(Path(...), settings=None)`` now resolves +
  reads (in-process callers are trusted; the audit's attack vector was
  the MCP/HTTP exposure). The MCP tool ``kaos-graph-load-rdf``
  enforces ``settings.allowed_root`` explicitly and refuses without it.
- **#2 (DoS caps post-hoc) — FIXED.** ``all_simple_paths`` now applies
  ``max_paths`` to the petgraph iterator via ``.take(max_paths)`` so
  enumeration stops at the cap (bounds peak CPU/memory, not just the
  returned list). ``maximal_cliques`` adds an upfront
  ``max_input_nodes`` gate (default 1000) — Bron-Kerbosch's worst case
  is 3^(N/3) cliques, so refusing oversized inputs at entry prevents
  exponential CPU/memory before the algorithm starts.
- **#3 (MCP handlers bypassed settings) — FIXED.** Every MCP tool's
  ``execute()`` now threads ``KaosGraphSettings.from_context(context)``
  into ``Graph.from_json`` so caps reflect per-request overrides instead
  of standalone defaults. ``kaos-graph-create``'s raw ``json.loads``
  path canonicalizes to the wire shape and re-feeds ``Graph.from_json``
  so the same capped codepath handles every entry.
- **#4 (file size cap after read) — FIXED.** Explicit-format file
  loading now stats the file BEFORE reading; oversized files refuse
  without allocating.
- **#5 (Rust ``Graph::from_json`` uncapped) — DOCUMENTED, defer rename.**
  Bare ``from_json(data)`` retained as a trusted-input ergonomic alias
  for ``from_json_capped(data, usize::MAX, ...)``; docstring flags
  untrusted-input-unsafe and v0.2 rename to ``from_json_unchecked``.
- **#6 (cargo-deny key removed) — FIXED.** ``allow-osi-fsf-free`` knob
  was removed in cargo-deny v0.18. ``deny.toml`` now uses the allowlist
  as single source of truth + ``confidence-threshold = 0.93``.
- **#7 (RUSTSEC-2026-0097 / rand 0.9.2 via oxrdf) — IGNORED w/ justification.**
  Transitive only; no direct use of the affected ``rand::rng()`` path
  in kaos-graph (RDF parsing is deterministic). Tracked upstream at
  oxigraph/oxigraph; ``deny.toml`` ``[advisories].ignore`` documents
  the waiver and review date.

38 regression tests in ``tests/security/test_audit_a2.py``; FOLIO
benchmark test now actively runs (was silently skipped) via the
auto-downloading ``folio_owl_path`` fixture in ``tests/conftest.py``.

Second follow-up audit pass (post-A2-followup, 6 findings):

- **#1 (HIGH) — `label_propagation` infinite-loop DoS — FIXED.** Synchronous
  label propagation can oscillate forever on a 2-node graph with both
  nodes flipping each round. Hard iteration cap of ``MAX_ITERATIONS = 100``
  in ``rust/core/algorithms/community.rs`` matches the upstream-petgraph
  default and is well above typical convergence (~10-20 iter). Confirmed
  the original DoS reproducer (5s timeout) now exits cleanly.
- **#2 (HIGH) — MCP raw `json.loads` cap bypass — FIXED.** The audit
  follow-up #3 fix capped ``Graph.from_json`` but missed three sibling
  tools that called ``json.loads`` directly: ``kaos-graph-load-adjacency``,
  ``kaos-graph-trace-to-graph``, and ``kaos-graph-validate-schema``.
  Added a shared ``_capped_json_loads(data, context, kind)`` helper in
  ``tools.py`` that gates every MCP-side parse on
  ``KaosGraphSettings.max_bytes`` from the request context. All four
  paths now share the same byte-cap surface.
- **#3 (HIGH) — SPARQL evaluation unbounded — FIXED.**
  ``query_sparql`` / ``query_sparql_ask`` now accept ``settings=`` with
  caps on ``max_query_bytes`` (default 64 KiB), ``max_rows`` (default
  100_000, surfaced via ``SparqlResult.truncated``), and ``max_time_s``
  (default 30 s wall-clock via ``signal.SIGALRM`` on POSIX). The
  ``kaos-graph-sparql`` MCP tool threads the request settings through.
  New ``KaosGraphSettings`` fields: ``max_query_bytes``, ``max_rows``,
  ``max_time_s``. New exception ``SparqlTimeoutError`` (subclass of
  ``TimeoutError``).
- **#4 (MED) — TOCTOU caveat on `_check_allowlist` — DOCUMENTED.**
  ``resolve(strict=True)`` is the standard POSIX symlink-follow-and-
  verify check, but the file is opened later in
  ``_load_file`` / Rust ``load_rdf_file_capped``. Docstring now spells
  out the threat-model contract (``allowed_root`` must be a directory
  the attacker cannot write to). Closing the window completely requires
  ``O_NOFOLLOW`` semantics with an fd-based open, which Python's
  ``Path.read_bytes`` does not expose; the v0.1 mitigation defers to
  OS-level capabilities (chroot, namespaces, AppArmor) for stricter
  guarantees.
- **#5 (MED) — ty unresolved-import on optional siblings — FIXED at
  Phase B5 strip.** ``# ty: ignore[unresolved-import]`` markers on
  every lazy sibling import (kaos_content, kaos_llm_core, kaos_mcp);
  ``tests/unit/test_programs.py`` excluded from ``[tool.ty.src]``
  because the kaos-llm-core integration path is opt-in extras and
  re-included in 0.1.0a2 once kaos-llm-core publishes.
- **#6 (MED) — uv.lock tracked-vs-gitignored — FIXED at Phase B5
  strip.** uv.lock is now gitignored in the per-module repo (``[mcp]``,
  ``[programs]``, ``[tabular]`` extras can't lock until the sibling
  packages publish). Re-added in 0.1.0a2 alongside those extras.

Total regression tests: 41 (in ``tests/security/test_audit_a2.py``).

First public alpha. Foundational graph library for the Kelvin Agentic
Operating System: high-performance Rust core with a typed Python API,
backed by `petgraph::StableDiGraph` and `oxrdf`/`oxrdfio`.

### Added

- **Rust core** (`rust/core/`) — pure-Rust graph engine with string-keyed
  nodes, JSON-valued node and edge properties, and serde support.
  Thread-safe sparse PageRank (O((V+E)·n) instead of petgraph's
  O(V²·E·n)) — FOLIO (25K nodes): 7 ms vs petgraph's 105 s.
- **PyO3 bindings** (`rust/bindings/`) — typed dataclass returns at the
  module boundary; raw dict access is confined to `_to_*()` converters.
- **Python API** (`python/kaos_graph/`) — `Graph`, `Node`, `Edge`,
  `Triple`, `BfsNode`, `DfsEvent`. 40+ algorithms: traversal (BFS/DFS,
  topological sort), shortest paths (Dijkstra, A*, Bellman-Ford,
  Floyd-Warshall), centrality (PageRank, betweenness, closeness,
  eigenvector), community (Louvain, label propagation), connectivity
  (SCC, weakly-connected components, articulation points, bridges),
  paths (simple paths, all simple paths with cap, shortest path k-edges,
  Eulerian trails), structure (cycles, cliques, isomorphism, max flow).
- **RDF/SPARQL** — `oxrdf` + `oxrdfio` parsers (Turtle, N-Triples,
  N-Quads, RDF/XML, TriG); `pyoxigraph` SPARQL backend optional via
  `[rdf]` extra. RDF parsing happens entirely in Rust until the
  Python API boundary.
- **Knowledge-graph tools** — `Schema`, `KnowledgeGraph`, fact ingestion,
  reasoning rules, ontology bridges.
- **I/O** — JSON, GraphML, GEXF, edgelist, adjacency-list (round-trippable).
- **Bridges** — Polars `DataFrame` ↔ `Graph`, NetworkX bridge.
- **Storage** — VFS-backed `save_to_vfs` / `load_from_vfs`.
- **MCP tools** — 17 graph operations exposed over the Model Context
  Protocol. The `[mcp]` extra is **planned for v0.1.0a2** once the
  companion `kaos-mcp` and `kaos-core` packages publish to PyPI; until
  then, the MCP tool registration is unreachable from a stock
  `pip install kaos-graph` and the `kaos-graph-serve` script will exit
  with a clear "kaos-mcp is required" error. Same applies to the
  `[programs]` extra (kaos-llm-core) and `[tabular]` extra
  (kaos-content). The `[rdf]` extra (pyoxigraph for SPARQL) is live
  at v0.1.0a1.
- **CLI** — `kaos-graph` (administrative); `kaos-graph-serve` (HTTP server,
  optional).
- Python 3.13 + 3.14 support; `requires-python = ">=3.13"`.

### License

This release is the first to ship under the Apache License 2.0. Earlier
internal versions were proprietary.

[Unreleased]: https://github.com/273v/kaos-graph/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/273v/kaos-graph/releases/tag/v0.1.0a1
