# kaos-graph

> **Part of [Kelvin Agentic OS](https://kelvin.legal) (KAOS)** — open agentic
> infrastructure for legal work, built by
> [273 Ventures](https://273ventures.com).
> See the [full KAOS package map](https://github.com/273v) for the rest of the stack.

[![PyPI - Version](https://img.shields.io/pypi/v/kaos-graph)](https://pypi.org/project/kaos-graph/)
[![Python](https://img.shields.io/pypi/pyversions/kaos-graph)](https://pypi.org/project/kaos-graph/)
[![License](https://img.shields.io/pypi/l/kaos-graph)](https://github.com/273v/kaos-graph/blob/main/LICENSE)
[![CI](https://github.com/273v/kaos-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/273v/kaos-graph/actions/workflows/ci.yml)

`kaos-graph` is a high-performance graph library for KAOS — a typed Python
API over a pure-Rust core backed by
[petgraph](https://github.com/petgraph/petgraph) and the
[oxrdf](https://github.com/oxigraph/oxigraph) RDF engine. It provides the
graph-algorithm and knowledge-graph building blocks the rest of the stack
relies on: 40+ algorithms (PageRank, shortest paths, centrality, community
detection, DAG ops), RDF/SPARQL parsing, and typed Python wrappers
throughout.

It is dependency-light: the BASE install pulls only `kaos-graph` itself
plus `defusedxml` (~250 KB pure-Python). Optional extras layer in the
rest of the KAOS ecosystem.

## Install

```bash
uv add "kaos-graph>=0.1.0"
# or
pip install "kaos-graph>=0.1.0"
```

`kaos-graph` requires Python **3.13** or newer. The published wheels
are `cp313-abi3` — one wheel per OS/architecture covers every CPython
3.13+ minor (3.13, 3.14, 3.15, …). No re-release needed when 3.15 ships.

Platform coverage: Linux x86_64 (manylinux + musllinux), Linux aarch64
(manylinux + musllinux), macOS arm64, Windows x86_64, Windows arm64.

## Quick start

```python
from kaos_graph import Graph
from kaos_graph.algorithms import pagerank, shortest_paths, topological_sort

g = Graph()
g.add_node("alice", role="engineer")
g.add_node("bob", role="manager")
g.add_edge("alice", "bob", relationship="reports_to")

# Algorithms
ranks = pagerank(g)
costs = shortest_paths(g, "alice")
order = topological_sort(g)
```

## Concepts

The package is built around a small set of typed primitives.

| Concept | What it is |
|---|---|
| **`Graph`** | Property graph backed by `petgraph::StableDiGraph`. String-keyed nodes with JSON-valued properties; edges with arbitrary properties; multi-graph semantics opt-in. Stable node refs across mutations (additions/removals don't invalidate handles). |
| **`Node` / `Edge` / `Triple`** | Typed dataclass results emitted at the FFI boundary. `Node(id, properties)`, `Edge(source, target, properties)`, `Triple(subject, predicate, object)`. |
| **Algorithms** | 40+ functions in `kaos_graph.algorithms` covering traversal (BFS/DFS, topological sort), shortest paths (Dijkstra, A*, Bellman-Ford, Floyd-Warshall), centrality (PageRank, betweenness, closeness, eigenvector), community (Louvain, label propagation), connectivity (SCC, weakly-connected, articulation points, bridges), structure (cycles, cliques, isomorphism, max flow), and DAG ops (longest path, critical path). |
| **Sparse PageRank** | O((V+E)·n) instead of petgraph's O(V²·E·n). FOLIO ontology (~25K nodes, ~36K edges): 7 ms vs petgraph's 105 s. The marketing-grade benchmark exercised on every CI run. |
| **RDF / SPARQL** | `oxrdf` + `oxrdfio` parsers (Turtle, N-Triples, N-Quads, RDF/XML, TriG) with byte / triple / size caps applied at the FFI boundary. SPARQL via `pyoxigraph` opt-in through the `[rdf]` extra. |
| **I/O & bridges** | JSON (round-trippable), GraphML / GEXF (defusedxml-hardened), edgelist, adjacency-list, mermaid, dot. NetworkX bridge; Polars / DuckDB tabular bridge available via the `[tabular]` extra. |
| **Knowledge graph** | `Schema`, `KnowledgeGraph`, fact ingestion, reasoning rules, ontology bridges. |
| **Storage** | VFS-backed `save_to_vfs` / `load_from_vfs` with name validation against namespace escape. |

## CLI

`kaos-graph` ships a `kaos-graph` administrative CLI plus an optional
`kaos-graph-serve` MCP server (loopback-only by default):

```bash
kaos-graph version          # version info
kaos-graph serve            # forwards to kaos-graph-serve (stdio MCP)
kaos-graph-serve            # MCP server, stdio transport
kaos-graph-serve --http     # MCP server, streamable HTTP (loopback only)
```

Note: 17 MCP tools are registered by `register_graph_tools()` and are
available with `pip install "kaos-graph[mcp]>=0.1.0"` (pulls in
`kaos-mcp`).

## Compatibility & status

| Aspect | |
|---|---|
| **Python** | 3.13, 3.14 (informational matrix entries for 3.14t free-threaded and 3.15-dev). One `cp313-abi3` wheel per OS/arch covers all 3.13+ minors. |
| **OS** | Linux (manylinux + musllinux, x86_64 + aarch64), macOS arm64, Windows x86_64, Windows arm64. macOS x86_64 deliberately skipped (Apple ended Intel sales in 2023). |
| **Maturity** | 0.1.0 GA. The public API is documented in `kaos_graph.__all__`. |
| **Stability policy** | Pre-1.0: minor bumps may change behaviour. Every change is documented in [`CHANGELOG.md`](CHANGELOG.md). |
| **Test coverage** | 173 Rust unit tests + 402 Python tests passing (575 total). 38 dedicated security regressions covering the audit-pass A2 + two follow-up rounds. |
| **Type checker** | Validated with [`ty`](https://docs.astral.sh/ty/), Astral's Python type checker. |

## Documentation

Per-package reference: [`docs/`](docs/) in this repo.

Cross-cutting KAOS guides (agentic patterns, persona presets, settings
policy, citations, MCP data flow, migration to 0.1.0 GA) live in
[`kaos-modules/docs/guides/`](https://github.com/273v/kaos-modules/tree/main/docs/guides).

## Companion packages

`kaos-graph` is one of the packages in the
[Kelvin Agentic OS](https://kelvin.legal). The broader stack:

| Package | Layer | What it does |
|---|---|---|
| [`kaos-core`](https://github.com/273v/kaos-core) | Core | Foundational runtime, MCP-native types, registries, execution engine, VFS |
| [`kaos-content`](https://github.com/273v/kaos-content) | Core | Typed document AST: Block/Inline, provenance, views |
| [`kaos-mcp`](https://github.com/273v/kaos-mcp) | Bridge | FastMCP server, `kaos` management CLI, MCP resource templates |
| [`kaos-pdf`](https://github.com/273v/kaos-pdf) | Extraction | PDF → AST with provenance |
| [`kaos-web`](https://github.com/273v/kaos-web) | Extraction | Web extraction, browser automation, search, domain intelligence |
| [`kaos-office`](https://github.com/273v/kaos-office) | Extraction | DOCX / PPTX / XLSX readers + writers to AST |
| [`kaos-tabular`](https://github.com/273v/kaos-tabular) | Extraction | DuckDB-powered SQL analytics |
| [`kaos-source`](https://github.com/273v/kaos-source) | Data | Government + financial data connectors (Federal Register, eCFR, EDGAR, GovInfo, PACER, GLEIF) |
| [`kaos-llm-client`](https://github.com/273v/kaos-llm-client) | LLM | Multi-provider LLM transport |
| [`kaos-llm-core`](https://github.com/273v/kaos-llm-core) | LLM | Typed LLM programming (Signatures, Programs, Optimizers) |
| [`kaos-nlp-core`](https://github.com/273v/kaos-nlp-core) | Primitives (Rust) | High-performance NLP primitives |
| [`kaos-nlp-transformers`](https://github.com/273v/kaos-nlp-transformers) | ML | Dense embeddings + retrieval |
| [`kaos-graph`](https://github.com/273v/kaos-graph) | Primitives (Rust) | Graph algorithms + RDF/SPARQL |
| [`kaos-ml-core`](https://github.com/273v/kaos-ml-core) | Primitives (Rust) | Classical ML on the document AST |
| [`kaos-citations`](https://github.com/273v/kaos-citations) | Legal | Legal citation extraction, resolution, verification |
| [`kaos-agents`](https://github.com/273v/kaos-agents) | Agentic | Agent runtime, memory, recipes |
| [`kaos-reference`](https://github.com/273v/kaos-reference) | Sample | Reference module for module authors |

Packages depend on `kaos-core`; everything else is opt-in. Mix and match the
ones you need.

## Development

```bash
git clone https://github.com/273v/kaos-graph
cd kaos-graph
uv sync --group dev --extra rdf
uv run maturin develop --release
```

Install pre-commit hooks (recommended — they run the same checks as CI on
every commit, scoped to staged files):

```bash
uvx pre-commit install
uvx pre-commit run --all-files     # one-time full sweep
```

Manual QA commands (the same set CI runs):

```bash
cargo fmt --check
cargo clippy --no-default-features --all-targets -- -D warnings
cargo test --no-default-features --lib
uv run ruff format --check python/kaos_graph tests
uv run ruff check python/kaos_graph tests
uv run ty check python/kaos_graph tests
uv run pytest tests/
```

## Build from source

```bash
uv build
uv pip install dist/*.whl
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md)
for setup, quality gates, pull request expectations, and engineering
standards. By contributing you agree to follow the
[project conduct expectations](CODE_OF_CONDUCT.md) and certify the
[Developer Certificate of Origin v1.1](https://developercertificate.org/) —
sign every commit with `git commit -s`. Please open an issue before starting
on a non-trivial change so we can align on scope.

## Security

For security issues, **please do not file a public issue**. Report privately
via [GitHub Private Vulnerability Reporting](https://github.com/273v/kaos-graph/security/advisories/new)
or email **security@273ventures.com**. See [SECURITY.md](SECURITY.md) for the
full disclosure policy.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

Copyright 2026 [273 Ventures LLC](https://273ventures.com).
Built for [kelvin.legal](https://kelvin.legal).
