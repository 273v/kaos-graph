# Changelog

All notable changes to `kaos-graph` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

## [0.1.3] — 2026-05-25

Dependabot batch — automated dep bumps. Skips 0.1.2 due to a busted
tag that was cancelled mid-Release (no PyPI publish occurred).

### Dependabot

- build(deps): bump serde_json 1.0.149 → 1.0.150 in cargo-minor group (#25)
- build(deps): bump github/codeql-action 4.35.5 → 4.36.0 in actions-all group (#26)
- build(deps): bump the deps-minor group with 7 updates (#27)

## [0.1.2] — 2026-05-25

Dependabot batch.

### Dependabot

- build(deps): bump serde_json 1.0.149 → 1.0.150 in cargo-minor group (#25)
- build(deps): bump github/codeql-action 4.35.5 → 4.36.0 in actions-all group (#26)
- build(deps): bump the deps-minor group with 7 updates (#27)

## [0.1.1] — 2026-05-23

### Added — `[mcp]`, `[tabular]`, `[programs]` extras declared

Declared three previously-undeclared optional-dependencies:

- `mcp = ["kaos-core>=0.1.0,<0.2", "kaos-mcp>=0.1.0,<0.2"]` — required
  by `kaos-graph-serve` (and referenced by `README.md:85-87`).
- `tabular = ["kaos-content>=0.1.0,<0.2"]` — required by the Polars /
  DuckDB tabular bridge (referenced by `README.md:69`).
- `programs = ["kaos-llm-core>=0.1.0,<0.2"]` — required by the
  trace-to-graph program tool (referenced by
  `python/kaos_graph/tools/_programs.py:73`).

The extras were already advertised by README, runtime tool errors, and
`kaos-modules/docs/guides/dependency-reference.md` but were not declared
because `kaos-mcp` / `kaos-content` / `kaos-llm-core` were not on PyPI
when v0.1.0a1 shipped. The 0.1.0 GA cascade resolved the prerequisite.

`tests/unit/test_serve_install_contract.py` pins the install contract:
`kaos-graph-serve` exits 1 with `[mcp]` and `kaos-graph[mcp]` in stderr
when `kaos-mcp` is unavailable.

Also updated `python/kaos_graph/serve.py` error message to cite the
canonical `pip install kaos-graph[mcp]` install hint instead of
`pip install kaos-core kaos-mcp`. Closes audit-04/kaos-graph.md F-001.

### Changed

- `pyproject.toml` classifier bumped from `Development Status :: 3 - Alpha`
  to `Development Status :: 5 - Production/Stable` to reflect the
  0.1.0 GA release (WU-L #543) that froze the public API for the
  0.1.x line. Closes audit-04/kaos-graph.md Family D (classifier drift).


## [0.1.0] — 2026-05-20

### Changed — WU-L of 0.1.0 GA plan

- 0.1.0 GA — WU-L of the 0.1.0 GA plan. First stable release of
  `kaos-graph`. The public Python + Rust API is frozen for the 0.1.x
  line: no breaking changes will land until 0.2.0. Only kaos-* pin is
  `kaos-core` in the dev group, raised from `>=0.1.0rc1,<0.2` to
  `>=0.1.0,<0.2`. Cargo crate version bumped from `0.1.0-rc.1` to
  `0.1.0`; maturin emits the PEP 440-normalized wheel metadata
  `0.1.0`. No source changes vs 0.1.0rc1.


## [0.1.0rc1] — 2026-05-20

### Changed — WU-J of 0.1.0 GA plan

- Release candidate cut per WU-J of the 0.1.0 GA plan. Freezes the
  public Python + Rust API surface ahead of GA. No source changes
  relative to 0.1.0-alpha.5; this release exists to raise the
  kaos-core dev-group pin floor to the rc track and signal API freeze
  to downstream consumers.
- Pin floor raised to `kaos-core>=0.1.0rc1,<0.2` across `kaos-*` deps
  in the dev group. The `<0.2` ceiling protects against legacy
  `0.2.0a*` lines (e.g. kaos-nlp-transformers) leaking into resolution.
- Cargo crate version bumped to `0.1.0-rc.1`; maturin emits the
  PEP 440-normalized wheel metadata `0.1.0rc1`.

### Verified
- Rust QA: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test --no-default-features` (173 passed).
- Python QA (with `--extra rdf`, matching `quality.yml`):
  `ruff format --check`, `ruff check`, `ty check`,
  `pytest -m "not live and not network and not slow and not integration"`
  (376 passed, 8 skipped — sibling packages not in default install).


## [0.1.0-alpha.5] — 2026-05-20

### Changed — kaos-core 0.1.0a12 catch-up (WU-D.3)

- Layer 1 Rust+Python catch-up release per the 0.1.0 GA plan
  (WU-D.3). No runtime source changes — `kaos-core` is dev-only for
  this package; the Rust graph/RDF core has no kaos-core dependency
  at the boundary, and the 0.1.0a10 URI redesign + 0.1.0a12
  capability type land cleanly.
- `uv.lock` refreshed: dev-group `kaos-core` 0.1.0a10 → 0.1.0a12.
- Linux x86_64 `maturin develop --release` build is green; CI matrix
  builds macOS arm64 + Windows wheels on tag push.

### Verified
- Rust QA: `cargo fmt`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test --no-default-features` (173 passed).
- Python QA (with `--extra rdf`, matching `quality.yml`):
  `ruff format --check`, `ruff check`, `ty check`,
  `pytest -m "not live and not network and not slow and not integration"`
  (376 passed, 8 skipped — sibling packages not in default install,
  54 deselected).

## [0.1.0-alpha.4] — 2026-05-15

### Fixed

- **`kaos-graph-walk.nodes` parameter now declares its element
  type.** Previously the schema was `type=array` with no `items`,
  which OpenAI's strict JSON Schema validator rejected with HTTP
  400 `invalid_function_parameters`, taking down the whole tool
  catalog for openai-provider turns. Now
  `items: {type: "string"}` because node IDs are strings.
  kaos-core 0.1.0a7's defensive `items: {}` floor is belt +
  suspenders.

## [0.1.0a3] — 2026-05-11

### Fixed

- **Tests: FOLIO ontology cache path is now portable across OSes.**
  ``tests/conftest.py`` and ``tests/bench_performance.py`` hardcoded
  ``Path("/tmp/FOLIO/FOLIO.owl")``. On Windows that resolves to
  ``\tmp\FOLIO\FOLIO.owl`` (a drive-relative path under the current
  drive root, which doesn't exist and isn't writable on a fresh
  runner). Switched both to ``Path(tempfile.gettempdir()) / "FOLIO" /
  "FOLIO.owl"``, which is ``/tmp/FOLIO/FOLIO.owl`` on POSIX (same as
  before) and ``%TEMP%\FOLIO\FOLIO.owl`` on Windows. Same downloader
  contract; no behavior change on existing POSIX runners. Files:
  ``tests/conftest.py``, ``tests/bench_performance.py``.
### Changed

- **uv.lock is now tracked in git.** Previously gitignored at v0.1.0a1
  because the ``[mcp]`` optional extra (and the ``kaos-mcp`` dev
  dependency) referenced a sibling not yet on PyPI; ``uv lock``
  couldn't resolve them. ``kaos-mcp`` shipped (0.1.0a2), so the
  original gating reason no longer applies. Tracking the lockfile
  gives reproducible local dev environments, lets Dependabot surface
  sibling-version bumps as PRs, and makes the supply-chain pin set
  publicly auditable. Mirrors the org-wide convention being adopted
  across all 16 kaos-* repos.
### Security

- **bandit + vulture now run in both pre-commit and CI.** The
  ``.pre-commit-config.yaml`` gains two new hooks (bandit static
  security scan + vulture dead-code scan), mirrored by jobs in
  ``security.yml`` so the scan is publicly visible on every PR.
  Bandit skip list is justified inline per audit
  (``B101,B404,B603,B607``); vulture runs at ``--min-confidence
  100`` with a shared ``--ignore-names`` list for framework
  callbacks / signal handlers / OAuth field names that vulture
  can't infer from the import graph alone. Both hooks currently
  pass clean. Mirrors the rollout pattern from kaos-core.

### Removed

- **musllinux wheels (Alpine Linux / musl libc)** dropped from the
  release.yml matrix. ``kaos_graph-*-cp313-abi3-musllinux_1_2_x86_64.whl``
  and ``-aarch64.whl`` will not ship on the next release. Rationale:
  family-consistency. ``kaos-nlp-transformers`` can't ship musllinux
  (ort's ``download-binaries`` feature pulls Microsoft's official
  libonnxruntime which is glibc-only); shipping musllinux for
  ``kaos-graph`` while the downstream ML sibling can't install there
  creates a fragmented Alpine user experience. The 0.1.0a2 release
  retains its musllinux wheels on PyPI; Alpine users requiring this
  package standalone should pin ``kaos-graph==0.1.0a2`` until the
  ML runtime constraint is lifted.

## [0.1.0a2] — 2026-05-07

### Security

Audit pass `audit-01` (7 findings reviewed; 5 fixed with regression tests, 1
already-correct, 1 invalidated by verification against the published PyPI
convention). Tests live in `tests/security/test_audit_01.py`.

- **KG-001 (HIGH) — `kaos-graph-load-adjacency` cap-bypass closed.** The
  MCP-reachable adjacency loader called `json.loads` and built the graph
  without any byte / node / edge ceiling, while the sibling
  `Graph.from_json` path was already capped via `KaosGraphSettings`. The
  loader now accepts an optional `settings=` keyword, pre-validates the
  raw payload's UTF-8 byte length (not character length) against
  `max_bytes`, and aborts construction the moment the running node or
  edge counter would exceed `max_nodes` / `max_edges`. The MCP tool
  threads `KaosGraphSettings.from_context(context)` through the call so
  per-request `_meta.kaos_config` overrides flow end-to-end. Implicit
  endpoints declared only inside `edges` count toward the node cap so
  the cap can't be side-stepped by omitting the `nodes` map.
- **KG-002 (MEDIUM) — `tests/unit` is now strictly hermetic.** The FOLIO
  ontology load lived under `tests/unit/test_rdf.py` and could pull a
  multi-MiB OWL file from GitHub on first run. The test moved to
  `tests/integration/test_folio_owl.py` with the `integration` marker;
  `tests/unit` no longer references `folio_owl_path`. A regression
  guard greps `tests/unit/*.py` for the fixture name and fails if it
  reappears.
- **KG-003 (MEDIUM) — SPARQL tests gated on `pyoxigraph`.** `TestSparql`
  carries a class-level `pytest.mark.skipif(find_spec("pyoxigraph") is
  None, …)` so a dev install without the optional `[rdf]` extra skips
  cleanly instead of failing at runtime. The check uses
  `importlib.util.find_spec` and is collection-safe.

### Changed

- **KG-004 — `tools.py` split by domain (1,765 lines → package).** The
  monolithic `register_graph_tools` is now a thin orchestrator over five
  domain modules: `_core` (5 tools), `_algorithms` (4), `_rdf` (3), `_io`
  (4), `_programs` (1). Shared lazy-import helpers live in `_common`.
  Public API is unchanged: `from kaos_graph.tools import
  register_graph_tools` resolves identically; `_ALGORITHMS`,
  `_EXPORT_FORMATS`, and the module-level `logger` remain accessible
  for the existing audit A2-#2 standalone-import test.
- **KG-005 — text / diagram tools return structured success.**
  `kaos-graph-export`, `kaos-graph-visualize`, and
  `kaos-graph-export-adjacency` previously returned the rendered string
  via bare `ToolResult.create_success(plain_text)`, dropping every
  piece of machine-readable metadata. They now return `output={format,
  output|diagram|adjacency_json, n_nodes, n_edges, n_bytes, …}` plus a
  one-line `summary=` so agents can read either the structured payload
  or the human summary. Test surface updated in `tests/unit/test_tools.py`
  and `tests/integration/test_mcp_graph_pipeline.py`. A regression
  guard in `tests/security/test_audit_01.py` rejects any
  `ToolResult.create_success(...)` in `python/kaos_graph/tools/` that
  omits `summary=`.
- **KG-006 — Rust crate-root lints + free-threaded PyO3 module.**
  `rust/lib.rs` now declares `#![warn(rust_2018_idioms,
  rust_2021_compatibility, unreachable_pub, unused_qualifications)]`
  per the standard in `docs/oss/30-rust-packaging/clippy-and-quality.md`,
  and the PyO3 root module is annotated `#[pymodule(gil_used = false)]`
  for free-threaded Python (PEP 703 / cpython-3.14t). The exposed
  `#[pyclass]` types own their state via `&mut self` borrows so the
  PyO3 borrow checker serializes mutations across threads without the
  GIL; no `RefCell` / `Mutex` / static globals exist. Fallout:
  `bindings/{algorithms,graph,knowledge,rdf}.rs` register-fns moved
  from `pub` to `pub(crate)`, `pyo3::PyAny` qualifier dropped in favor
  of the `prelude::*` import, two `std::collections` qualifiers
  cleaned up. `missing_docs` is allowed at the crate root with a
  tracking note pending a focused docs-backfill.

### Investigated, no change

- **KG-007 — package URL metadata.** The audit recommended flipping
  Cargo + pyproject URLs from `https://kelvin.legal` /
  `https://github.com/273v/kaos-graph` to
  `https://273ventures.com` / `https://github.com/273v/kaos-modules`.
  Verifying against the live `kaos-core 0.1.0a2` release on PyPI showed
  the actual published convention is the `kelvin.legal` + per-package
  shape, used by both monorepo and per-module copies of every shipped
  kaos-* package. The audit finding contradicted shipped reality and
  was not applied. A regression test (`TestPackageUrlMetadata`) pins
  the convention so a future "fix" can't drift the metadata away from
  what's already on PyPI.

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

35 regression tests in ``tests/security/test_audit_a2.py``; FOLIO
benchmark test now actively runs (was silently skipped) via the
auto-downloading ``folio_owl_path`` fixture in ``tests/conftest.py``.

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
- **MCP tools** (optional, `[mcp]` extra) — 17 graph operations exposed
  over the Model Context Protocol.
- **CLI** — `kaos-graph` (administrative); `kaos-graph-serve` (HTTP server,
  optional).
- Python 3.13 + 3.14 support; `requires-python = ">=3.13"`.

### License

This release is the first to ship under the Apache License 2.0. Earlier
internal versions were proprietary.

[Unreleased]: https://github.com/273v/kaos-graph/compare/v0.1.0a3...HEAD
[0.1.0a3]: https://github.com/273v/kaos-graph/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/273v/kaos-graph/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/273v/kaos-graph/releases/tag/v0.1.0a1
