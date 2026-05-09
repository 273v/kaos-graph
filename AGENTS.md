# Agent Guidance

## Scope

This file is the canonical repository-local guidance for coding agents
working in `kaos-graph`. Follow it together with:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [Python design and architecture](docs/standards/python-design-and-architecture.md)
- [Rust/PyO3 design and architecture](docs/standards/rust-pyo3-design-and-architecture.md)
- [Code quality standards](docs/standards/code-quality-standards.md)
- [Engineering process](docs/standards/engineering-process.md)
- [Tests, fixtures, and CI](docs/standards/tests-fixtures-ci.md)

Keep changes focused. Do not edit generated files, build artifacts,
release metadata, or unrelated docs as part of routine code work.

## Project Identity

`kaos-graph` is the distribution name. `kaos_graph` is the Python import
package. The project is a typed Python API over a Rust graph and RDF core
exposed through PyO3 and packaged with maturin.

The public surface includes names exported by `kaos_graph.__all__`,
documented modules, the `kaos-graph` and `kaos-graph-serve` CLIs,
optional RDF behavior, MCP tool contracts when enabled, serialized
formats, documented exceptions, and wheel/package metadata.

## Setup

Use Python 3.13 or newer and `uv`:

```bash
uv sync --group dev --extra rdf
uv run maturin develop --release
```

The package uses `ruff` for formatting and linting, `ty` for Python type
checking, `pytest` for Python tests, `cargo fmt`, `cargo clippy`, and
`cargo test` for Rust, and maturin for extension builds. Do not use
mypy as a substitute for `ty`.

## Local Checks

Run the checks that match the change. For normal Python-facing work:

```bash
uv run ruff format --check python/kaos_graph tests
uv run ruff check python/kaos_graph tests
uv run ty check python/kaos_graph tests
uv run pytest -m "not live and not network and not slow" --no-cov
```

For Rust or PyO3 work:

```bash
cargo fmt --check
cargo clippy --no-default-features --all-targets -- -D warnings
cargo test --no-default-features --lib
uv run maturin develop --release
uv run pytest -m "not live and not network and not slow" --no-cov
```

Before releases or packaging changes, follow the broader gates in
[CONTRIBUTING.md](CONTRIBUTING.md) and `docs/standards/*`, including
`cargo audit`, `cargo deny check`, `uv build`, and strict twine metadata
checks when applicable.

## Architecture Rules

Keep performance-critical graph, RDF, SPARQL, parsing, traversal,
ranking, and batch algorithms in the Rust core when they benefit from
Rust's speed, memory safety, or deterministic behavior. Keep Python
wrappers typed, ergonomic, and thin.

Maintain the layer boundaries:

- Rust core: pure Rust data structures, algorithms, RDF handling, and
  domain errors.
- PyO3 bindings: minimal conversion between Python and Rust types.
- Python wrappers: public API, typed result objects, docs, and
  package-specific exceptions.

Preserve PyO3, abi3, and maturin wheel behavior. `pyproject.toml` and
`Cargo.toml` intentionally align around `pyo3/abi3-py313` and
`kaos_graph._rust`; do not change this casually.

Convert Rust errors into agent-readable, package-specific Python
exceptions. Include useful bounded context, but never include secrets,
large payloads, raw untrusted bytes, or internal paths in user-facing
errors.

Avoid `unsafe` unless there is a narrow, documented reason and tests.
Keep ownership, lifetimes, GIL handling, and copies explicit at the
Rust/Python boundary.

## Graph And RDF Principles

Graph algorithms should be deterministic where tests or public formats
rely on ordering. If an algorithm has multiple valid orders, document the
chosen tie-breaking rule or normalize results at the boundary.

Preserve property graph semantics, RDF parser limits, SPARQL behavior,
serialization round trips, and CLI/MCP/public API contracts unless the
change is intentional, tested, documented, and reflected in the
changelog.

Bound untrusted input by size, node count, edge count, recursion,
iteration, and format-specific limits. Test malformed graph, RDF, XML,
and serialized inputs through the real public entry points.

## Testing

Test both Rust internals and Python boundary behavior for Rust/PyO3
changes. A Rust unit test alone is not enough when Python users observe
different conversion, exception, typing, ordering, or serialization
behavior.

Use realistic tests for public APIs, CLI behavior, RDF/SPARQL parsing,
graph I/O, storage, MCP tools, and security limits. Keep tests
deterministic and avoid live network or credential requirements in the
default gate.

## Security

Do not commit secrets, credentials, private data, virtual environments,
caches, or build output. Keep optional dependencies behind extras and
lazy imports. Use `defusedxml`-hardened paths for XML formats and
preserve path, VFS, RDF, parser, and size guards.

Report suspected vulnerabilities through `SECURITY.md`, not public
issues.

## Commits, PRs, And Releases

Use conventional commit messages and sign commits with DCO sign-off:

```bash
git commit -s -m "docs: update agent guidance"
```

Keep PRs to one logical change. Include what changed, why it changed,
how it was tested, and whether public API, CLI behavior, package
metadata, fixtures, security behavior, or release artifacts changed.

Rebase on `main` before opening or updating PRs. Do not force-push.
Release changes must follow the release, changelog, tag, build,
metadata, and smoke-test process in [CONTRIBUTING.md](CONTRIBUTING.md)
and [Engineering process](docs/standards/engineering-process.md).
