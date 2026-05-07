"""Regression tests for the kaos-graph audit-01 findings (KG-001 .. KG-007).

Each test corresponds to a finding in ``docs/audit-01/kaos-graph.md`` and
prevents the vulnerability or anti-pattern from re-appearing.
"""

from __future__ import annotations

import json

import pytest

# ────────────────────────────────────────────────────────────────────────────
# KG-001: kaos-graph-load-adjacency must enforce KaosGraphSettings caps
# ────────────────────────────────────────────────────────────────────────────


class _CapsSettings:
    """Duck-typed stand-in for ``KaosGraphSettings`` used in cap tests."""

    __slots__ = ("max_bytes", "max_edges", "max_nodes")

    def __init__(self, *, max_bytes: int = 10**9, max_nodes: int = 10**9, max_edges: int = 10**9):
        self.max_bytes = max_bytes
        self.max_nodes = max_nodes
        self.max_edges = max_edges


class TestAdjacencyLoaderCaps:
    """KG-001: ``load_adjacency_json`` rejects oversize / over-cap payloads.

    The audit verdict was that ``kaos-graph-load-adjacency`` accepted untrusted
    MCP JSON via an uncapped ``json.loads`` plus uncapped graph construction,
    bypassing the cap path used by ``Graph.from_json``. These tests pin the
    cap behaviour at the library layer; ``TestAdjacencyMcpToolThreadsSettings``
    pins the MCP tool layer.
    """

    def test_max_bytes_enforced(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        payload = '{"nodes": {"a": {}}}'  # 19 bytes
        with pytest.raises(ValueError, match=r"max_bytes is 5"):
            load_adjacency_json(payload, settings=_CapsSettings(max_bytes=5))

    def test_max_bytes_counts_utf8_bytes_not_characters(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        payload = json.dumps({"nodes": {"node-😀": {}}}, ensure_ascii=False)
        assert len(payload.encode("utf-8")) > len(payload)
        with pytest.raises(ValueError, match=r"max_bytes is \d+"):
            load_adjacency_json(payload, settings=_CapsSettings(max_bytes=len(payload)))

    def test_max_nodes_enforced_via_nodes_dict(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        payload = json.dumps({"nodes": {"a": {}, "b": {}, "c": {}}, "edges": {}})
        with pytest.raises(ValueError, match=r"more than 2 nodes"):
            load_adjacency_json(payload, settings=_CapsSettings(max_nodes=2))

    def test_max_nodes_enforced_via_implicit_edge_endpoints(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        # Endpoints declared only inside ``edges`` count toward max_nodes —
        # otherwise an attacker could side-step the cap by skipping ``nodes``.
        payload = json.dumps({"nodes": {}, "edges": {"a": [["b", {}], ["c", {}]]}})
        with pytest.raises(ValueError, match=r"more than 2 nodes"):
            load_adjacency_json(payload, settings=_CapsSettings(max_nodes=2))

    def test_max_edges_enforced(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        payload = json.dumps(
            {"nodes": {"a": {}, "b": {}, "c": {}}, "edges": {"a": [["b", {}], ["c", {}]]}}
        )
        with pytest.raises(ValueError, match=r"more than 1 edges"):
            load_adjacency_json(payload, settings=_CapsSettings(max_edges=1))

    def test_default_caps_allow_normal_use(self) -> None:
        from kaos_graph import Graph
        from kaos_graph.io.adjacency import load_adjacency_json, to_adjacency_json

        g = Graph(directed=True)
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b", weight=1.0)
        # No settings -> conservative built-in defaults; should comfortably fit.
        g2 = load_adjacency_json(to_adjacency_json(g))
        assert g2.n_nodes == 2
        assert g2.n_edges == 1

    def test_top_level_must_be_object(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        with pytest.raises(ValueError, match="JSON object at top level"):
            load_adjacency_json("[]")

    def test_nodes_must_be_object(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        with pytest.raises(ValueError, match="'nodes' must be a JSON object"):
            load_adjacency_json('{"nodes": ["a"]}')

    def test_edges_must_be_object(self) -> None:
        from kaos_graph.io.adjacency import load_adjacency_json

        with pytest.raises(ValueError, match="'edges' must be a JSON object"):
            load_adjacency_json('{"nodes": {}, "edges": []}')


class TestAdjacencyMcpToolThreadsSettings:
    """KG-001: ``kaos-graph-load-adjacency`` MCP tool threads settings.

    Per the configuration hierarchy, MCP callers can override caps via
    ``KaosContext._config['kaos_config']`` (e.g. ``{"max_nodes": 1}``). The
    tool must apply those overrides before calling into ``json.loads``.
    """

    @pytest.fixture()
    def load_tool(self):  # type: ignore[no-untyped-def]
        try:
            from kaos_core.base.tool import KaosTool
        except ImportError:
            pytest.skip("kaos-core not installed")

        from kaos_graph.tools import register_graph_tools

        class MockToolRegistry:
            def __init__(self) -> None:
                self.tools: dict[str, KaosTool] = {}

            def register_tool(self, tool: KaosTool) -> None:
                self.tools[tool.metadata.name] = tool

        class MockRuntime:
            def __init__(self) -> None:
                self.tools = MockToolRegistry()

        runtime = MockRuntime()
        register_graph_tools(runtime)
        return runtime.tools.tools["kaos-graph-load-adjacency"]

    @pytest.mark.asyncio
    async def test_per_request_max_bytes_override_rejects_payload(self, load_tool) -> None:  # type: ignore[no-untyped-def]
        try:
            from kaos_core.base.context import KaosContext
        except ImportError:
            pytest.skip("kaos-core not installed")

        adjacency = json.dumps({"nodes": {"a": {}, "b": {}}, "edges": {"a": [["b", {}]]}})
        # Force a 1-byte cap via per-request config; oversize payload must be
        # refused with a structured error rather than being loaded.
        ctx = KaosContext(session_id="test-kg-001", config={"max_bytes": 1})
        result = await load_tool.execute({"adjacency_json": adjacency}, context=ctx)
        assert result.isError
        # The error text should hint at the cap so an agent can self-correct.
        assert "max_bytes" in (result.text or "")

    @pytest.mark.asyncio
    async def test_per_request_max_nodes_override_rejects_payload(self, load_tool) -> None:  # type: ignore[no-untyped-def]
        try:
            from kaos_core.base.context import KaosContext
        except ImportError:
            pytest.skip("kaos-core not installed")

        adjacency = json.dumps({"nodes": {"a": {}, "b": {}, "c": {}, "d": {}}, "edges": {}})
        ctx = KaosContext(session_id="test-kg-001", config={"max_nodes": 2})
        result = await load_tool.execute({"adjacency_json": adjacency}, context=ctx)
        assert result.isError
        assert "nodes" in (result.text or "").lower()

    @pytest.mark.asyncio
    async def test_per_request_max_edges_override_rejects_payload(self, load_tool) -> None:  # type: ignore[no-untyped-def]
        try:
            from kaos_core.base.context import KaosContext
        except ImportError:
            pytest.skip("kaos-core not installed")

        adjacency = json.dumps(
            {
                "nodes": {"a": {}, "b": {}, "c": {}},
                "edges": {"a": [["b", {}], ["c", {}]]},
            }
        )
        ctx = KaosContext(session_id="test-kg-001", config={"max_edges": 1})
        result = await load_tool.execute({"adjacency_json": adjacency}, context=ctx)
        assert result.isError
        assert "edges" in (result.text or "").lower()

    @pytest.mark.asyncio
    async def test_default_caps_allow_normal_request(self, load_tool) -> None:  # type: ignore[no-untyped-def]
        adjacency = json.dumps({"nodes": {"a": {}, "b": {}}, "edges": {"a": [["b", {}]]}})
        result = await load_tool.execute({"adjacency_json": adjacency})
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["n_nodes"] == 2
        assert result.structuredContent["n_edges"] == 1


# ────────────────────────────────────────────────────────────────────────────
# KG-002: tests/unit must be hermetic — FOLIO test lives in tests/integration
# ────────────────────────────────────────────────────────────────────────────


class TestUnitTestsAreHermetic:
    """KG-002: ``tests/unit`` must not depend on network-fetched fixtures."""

    def test_no_unit_test_uses_folio_owl_path(self) -> None:
        """Grep all tests/unit/*.py — none should reference ``folio_owl_path``.

        The fixture itself can pull a multi-MiB OWL file from GitHub. Any
        test that takes it as a parameter is implicitly a network test, so
        the contract is: it lives under ``tests/integration/``.
        """
        import pathlib

        # Resolve relative to this file so the test is location-independent.
        unit_dir = pathlib.Path(__file__).resolve().parent.parent / "unit"
        offenders: list[str] = []
        for py in unit_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "folio_owl_path" in text:
                offenders.append(str(py.relative_to(unit_dir.parent)))
        assert not offenders, (
            "tests/unit must not reference the FOLIO fixture; move these "
            f"tests to tests/integration/: {offenders}"
        )


# ────────────────────────────────────────────────────────────────────────────
# KG-003: SPARQL tests must be gated on pyoxigraph
# ────────────────────────────────────────────────────────────────────────────


class TestSparqlTestsGatedOnPyoxigraph:
    """KG-003: ``TestSparql`` skips when ``pyoxigraph`` is missing."""

    def test_sparql_class_carries_skipif_pytestmark(self) -> None:
        """The class-level ``pytestmark`` lists a skipif keyed on pyoxigraph.

        We don't need pyoxigraph to be installed to verify this — we just
        confirm the class declares the gate, so a fresh contributor running
        ``pytest tests/unit`` without the ``rdf`` extra still gets a clean
        skip rather than an ImportError.
        """
        from tests.unit import test_rdf

        marks = getattr(test_rdf.TestSparql, "pytestmark", None)
        assert marks, (
            "TestSparql must declare a class-level pytestmark; otherwise "
            "the SPARQL tests fail on installs without the rdf extra."
        )
        # pytestmark may be a single Mark or a list of Marks.
        if not isinstance(marks, list):
            marks = [marks]
        names = {m.name for m in marks}
        assert "skipif" in names, (
            "TestSparql.pytestmark must include a skipif keyed on pyoxigraph; "
            f"saw markers: {sorted(names)}."
        )


# ────────────────────────────────────────────────────────────────────────────
# KG-004: tools.py split by domain
# ────────────────────────────────────────────────────────────────────────────


class TestToolsModuleSplit:
    """KG-004: the MCP tool surface is split into domain modules."""

    def test_tools_py_split_into_package_modules(self) -> None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        assert not (root / "python/kaos_graph/tools.py").exists()
        for module_name in [
            "__init__.py",
            "_algorithms.py",
            "_common.py",
            "_core.py",
            "_io.py",
            "_programs.py",
            "_rdf.py",
        ]:
            assert (root / "python/kaos_graph/tools" / module_name).is_file()


# ────────────────────────────────────────────────────────────────────────────
# KG-005: text / visualization tools include summaries
# ────────────────────────────────────────────────────────────────────────────


class TestToolSuccessSummaries:
    """KG-005: ``create_success`` calls include human-readable summaries."""

    def test_tool_create_success_calls_have_summary(self) -> None:
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for py in (root / "python/kaos_graph/tools").glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "create_success":
                    continue
                has_summary = any(keyword.arg == "summary" for keyword in node.keywords)
                if not has_summary:
                    offenders.append(f"{py.relative_to(root)}:{node.lineno}")
        assert not offenders, f"ToolResult.create_success calls missing summary: {offenders}"


# ────────────────────────────────────────────────────────────────────────────
# KG-006: Rust warning lint set + PyO3 free-threaded annotation
# ────────────────────────────────────────────────────────────────────────────


class TestRustLintAndPyo3Annotation:
    """KG-006: crate root documents lints and declares PyO3 GIL use."""

    def test_crate_root_has_warning_lints_and_gil_annotation(self) -> None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2]
        lib_rs = (root / "rust/lib.rs").read_text(encoding="utf-8")
        assert "#![warn(rust_2018_idioms)]" in lib_rs
        assert "#![warn(rust_2021_compatibility)]" in lib_rs
        assert "#![warn(unreachable_pub)]" in lib_rs
        assert "#![warn(unused_qualifications)]" in lib_rs
        assert "#[pymodule(gil_used = false)]" in lib_rs


# ────────────────────────────────────────────────────────────────────────────
# KG-007: package URL metadata matches the published kaos-* convention
# ────────────────────────────────────────────────────────────────────────────
#
# The audit recommended flipping kaos-graph's URLs to the monorepo target
# (github.com/273v/kaos-modules + 273ventures.com / docs.273ventures.com).
# Verifying against the live kaos-core release on PyPI showed the actual
# convention is the per-package shape (kelvin.legal + github.com/273v/<pkg>),
# used by both monorepo and per-module copies of every published kaos-*
# package. The audit finding was incorrect; this test pins the real
# convention so a future "fix" doesn't drift the metadata away from what's
# already on PyPI.


class TestPackageUrlMetadata:
    """KG-007: Cargo and pyproject URL metadata match the published convention."""

    def test_pyproject_urls_match_published_convention(self) -> None:
        import pathlib
        import tomllib

        root = pathlib.Path(__file__).resolve().parents[2]
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        urls = pyproject["project"]["urls"]
        assert urls["Homepage"] == "https://kelvin.legal"
        assert urls["Documentation"] == "https://docs.kelvin.legal"
        assert urls["Repository"] == "https://github.com/273v/kaos-graph"
        assert urls["Issues"] == "https://github.com/273v/kaos-graph/issues"
        assert urls["Changelog"] == "https://github.com/273v/kaos-graph/blob/main/CHANGELOG.md"
        # Guard against the audit's wrong recommendation creeping back in.
        assert "273ventures.com" not in str(urls)
        assert "kaos-modules" not in str(urls)

    def test_cargo_urls_match_published_convention(self) -> None:
        import pathlib
        import tomllib

        root = pathlib.Path(__file__).resolve().parents[2]
        cargo = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
        package = cargo["package"]
        assert package["homepage"] == "https://kelvin.legal"
        assert package["documentation"] == "https://docs.kelvin.legal"
        assert package["repository"] == "https://github.com/273v/kaos-graph"
        url_keys = {"homepage", "documentation", "repository"}
        url_values = " ".join(value for key, value in package.items() if key in url_keys)
        assert "273ventures.com" not in url_values
        assert "kaos-modules" not in url_values
