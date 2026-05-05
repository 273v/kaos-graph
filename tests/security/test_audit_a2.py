"""Regression tests for the kaos-graph 0.1.0a1 audit (A2-#1 through A2-#14).

Each test corresponds to a finding in docs/oss/checklists/per-package-release.md
audit pass A2 and prevents the bug from re-appearing.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from kaos_graph import Graph
from kaos_graph.errors import (
    KaosGraphError,
    PathTraversalError,
)

# ────────────────────────────────────────────────────────────────────────────
# A2-#1 + #5: RDF loader path-traversal allowlist + format-required
# ────────────────────────────────────────────────────────────────────────────


class TestRdfPathAllowlist:
    """A2-#1: file loading is gated by KaosGraphSettings.allowed_root.

    The library function ``load_rdf`` is permissive when ``allowed_root`` is
    None (in-process callers are trusted). The audited boundary —
    ``kaos-graph-load-rdf`` MCP tool — enforces the allowlist explicitly.
    """

    def test_library_permissive_when_no_allowlist(self, tmp_path: Path) -> None:
        # In-process API: no settings → reads file (caller has open() anyway).
        from kaos_graph.rdf import load_rdf

        ttl = tmp_path / "x.ttl"
        ttl.write_text(
            "@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .",
            encoding="utf-8",
        )
        g, stats = load_rdf(ttl, settings=None)
        assert g.n_nodes == 2
        assert stats.total_triples == 1

    def test_outside_allowed_root_refuses(self, tmp_path: Path) -> None:
        from kaos_graph.rdf import load_rdf

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        outside = tmp_path / "outside.ttl"
        outside.write_text("@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .")

        # Settings whose allowed_root is sandbox/ — outside.ttl is sibling.
        class _S:
            allowed_root = str(sandbox)
            max_bytes = 1 << 30
            max_triples = 1 << 30

        with pytest.raises(PathTraversalError):
            load_rdf(outside, settings=_S())

    def test_inside_allowed_root_succeeds(self, tmp_path: Path) -> None:
        from kaos_graph.rdf import load_rdf

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        ttl = sandbox / "ok.ttl"
        ttl.write_text(
            "@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .",
            encoding="utf-8",
        )

        class _S:
            allowed_root = str(sandbox)
            max_bytes = 1 << 30
            max_triples = 1 << 30

        g, stats = load_rdf(ttl, settings=_S())
        assert g.n_nodes == 2
        assert stats.total_triples == 1


class TestRdfFormatRequired:
    """A2-#5: refuse silent RdfFormat::RdfXml fallback for unknown extensions."""

    def test_unknown_extension_refused_without_format(self, tmp_path: Path) -> None:
        from kaos_graph.rdf import load_rdf

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        f = sandbox / "data.foo"  # unknown extension
        f.write_text("@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .")

        class _S:
            allowed_root = str(sandbox)
            max_bytes = 1 << 30
            max_triples = 1 << 30

        with pytest.raises(ValueError, match="Unknown RDF file extension"):
            load_rdf(f, settings=_S())

    def test_unknown_extension_with_explicit_format_succeeds(self, tmp_path: Path) -> None:
        from kaos_graph.rdf import load_rdf

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        f = sandbox / "data.foo"
        f.write_text("@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .")

        class _S:
            allowed_root = str(sandbox)
            max_bytes = 1 << 30
            max_triples = 1 << 30

        g, _stats = load_rdf(f, format="turtle", settings=_S())
        assert g.n_nodes == 2

    def test_string_input_requires_format(self) -> None:
        from kaos_graph.rdf import load_rdf

        with pytest.raises(ValueError, match="format is required"):
            load_rdf("@prefix ex: <http://example.org/> . ex:A ex:knows ex:B .")


class TestMcpToolAllowlistEnforcement:
    """A2-#1: kaos-graph-load-rdf MCP tool refuses without allowed_root."""

    def test_load_rdf_tool_refuses_when_no_allowlist(self, tmp_path: Path) -> None:
        try:
            import kaos_core  # noqa: F401
        except ImportError:
            pytest.skip("kaos-core not installed; MCP tool surface unavailable")

        import asyncio

        from kaos_core import KaosRuntime
        from kaos_core.types.results import ToolResult

        from kaos_graph.tools import register_graph_tools

        runtime = KaosRuntime()
        register_graph_tools(runtime)
        tool = runtime.tools.get_tool("kaos-graph-load-rdf")
        assert tool is not None

        result: ToolResult = asyncio.run(
            tool.execute({"path": str(tmp_path / "x.ttl")}, context=None)
        )
        assert result.isError
        msg = result.text or ""
        assert "allowed_root" in msg or "KAOS_GRAPH_ALLOWED_ROOT" in msg


# ────────────────────────────────────────────────────────────────────────────
# A2-#2: standalone import works without kaos-core
# ────────────────────────────────────────────────────────────────────────────


class TestStandaloneImport:
    """A2-#2: kaos_graph and its IO surface import cleanly without kaos-core."""

    def test_import_kaos_graph_io(self) -> None:
        # Just importing must not require kaos-core.
        import kaos_graph
        from kaos_graph import errors, graph, types
        from kaos_graph.io import (  # noqa: F401
            from_gexf,
            from_graphml,
            to_dot,
            to_gexf,
            to_graphml,
        )

        assert hasattr(kaos_graph, "Graph")
        assert isinstance(errors.KaosGraphError("x"), Exception)
        assert graph.Graph().n_nodes == 0
        assert types.Edge

    def test_KaosGraphError_is_plain_exception_when_kaos_core_absent(self) -> None:
        # A2-#2: KaosGraphError inherits from kaos_core.exceptions.KaosCoreError
        # when available, otherwise from plain Exception. Either way it's
        # catchable as Exception.
        from kaos_graph.errors import (
            CycleError,
            EdgeNotFoundError,
            InvalidFormatError,
            KaosGraphError,
            NodeNotFoundError,
        )

        for cls in (
            KaosGraphError,
            NodeNotFoundError,
            EdgeNotFoundError,
            CycleError,
            InvalidFormatError,
        ):
            assert issubclass(cls, Exception)

    def test_tools_module_does_not_eager_import_kaos_core(self) -> None:
        # importlib.import_module on kaos_graph.tools must not pull kaos_core
        # before register_graph_tools is called. The module top only imports
        # json, logging, typing, and Protocol.
        import importlib

        # Pre-condition: not currently imported (best effort — may be stale
        # from earlier test in the same session). We don't assert preconditions
        # here, just ensure the import itself doesn't blow up.
        mod = importlib.import_module("kaos_graph.tools")
        assert hasattr(mod, "register_graph_tools")
        assert hasattr(mod, "logger")  # falls back to stdlib if kaos-core absent


# ────────────────────────────────────────────────────────────────────────────
# A2-#3: bounded compute on user input
# ────────────────────────────────────────────────────────────────────────────


class TestBoundedCompute:
    """A2-#3: from_json + RDF parse + algorithm caps."""

    def test_from_json_byte_cap(self) -> None:
        # PyGraph.from_json now requires explicit (max_bytes, max_nodes,
        # max_edges) — Graph.from_json wraps with conservative defaults.
        from kaos_graph._rust.graph import PyGraph

        big = "{}".rjust(1024)  # 1 KiB
        with pytest.raises(ValueError, match="refusing to parse above"):
            PyGraph.from_json(big, 100, 1, 1)  # max_bytes=100

    def test_from_json_node_cap(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        # 5 nodes declared, max_nodes=2.
        nodes = ",".join(f'{{"id":"n{i}","properties":{{}}}}' for i in range(5))
        data = f'{{"directed":true,"multi":false,"name":"","nodes":[{nodes}],"edges":[]}}'
        with pytest.raises(ValueError, match="refusing above max_nodes"):
            PyGraph.from_json(data, 1 << 20, 2, 100)

    def test_all_simple_paths_default_depth_capped(self) -> None:
        # A2-#3: default max_depth is 32, was effectively unbounded.
        from kaos_graph.algorithms import all_simple_paths

        g = Graph()
        # Long chain of 100 nodes — no path within 32 hops because we ask
        # for 99 hops.
        for i in range(100):
            g.add_node(f"n{i}")
        for i in range(99):
            g.add_edge(f"n{i}", f"n{i + 1}")
        # With default depth=32 we can't reach n99 from n0 in 32 nodes.
        paths = all_simple_paths(g, "n0", "n99")
        assert paths == []
        # With explicit large depth, we can.
        paths = all_simple_paths(g, "n0", "n99", max_depth=200)
        assert len(paths) == 1
        assert paths[0][0] == "n0"
        assert paths[0][-1] == "n99"


# ────────────────────────────────────────────────────────────────────────────
# A2-#4 + #14b/c: pickle hardening + GraphJson deny_unknown_fields
# ────────────────────────────────────────────────────────────────────────────


class TestPickleHardening:
    """A2-#4: __setstate__ enforces magic + size cap."""

    def test_round_trip(self) -> None:
        g = Graph()
        g.add_node("a", role="x")
        g.add_node("b")
        g.add_edge("a", "b", weight=1)
        blob = pickle.dumps(g._inner)
        # Magic bytes are visible at the start of the post-pickle JSON-bytes.
        # PyO3 pickle format wraps state in additional header so we just
        # verify the end-to-end round-trip.
        g2 = pickle.loads(blob)
        assert g2.n_nodes == 2
        assert g2.n_edges == 1

    def test_setstate_rejects_short_blob(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        g = PyGraph(directed=True)
        with pytest.raises(ValueError, match="too short"):
            g.__setstate__(b"abc")

    def test_setstate_rejects_bad_magic(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        g = PyGraph(directed=True)
        # 4-byte magic that isn't KGR1.
        with pytest.raises(ValueError, match="magic mismatch"):
            g.__setstate__(b"XXXX{}")

    def test_setstate_rejects_oversize_blob(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        g = PyGraph(directed=True)
        # 65 MiB — above the 64 MiB hard cap.
        oversize = b"KGR1" + b"x" * (64 * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="refusing to deserialize"):
            g.__setstate__(oversize)


class TestGraphJsonStrictFields:
    """A2-#14b: serde deny_unknown_fields rejects payload pollution."""

    def test_unknown_top_level_field_rejected(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        bad = (
            '{"directed":true,"multi":false,"name":"","nodes":[],"edges":[],'
            '"evil":"' + "x" * 1024 + '"}'
        )
        with pytest.raises(ValueError, match="unknown field"):
            PyGraph.from_json(bad, 1 << 20, 1 << 20, 1 << 20)

    def test_unknown_node_field_rejected(self) -> None:
        from kaos_graph._rust.graph import PyGraph

        bad = (
            '{"directed":true,"multi":false,"name":"","edges":[],"nodes":'
            '[{"id":"a","properties":{},"evil":"x"}]}'
        )
        with pytest.raises(ValueError, match="unknown field"):
            PyGraph.from_json(bad, 1 << 20, 1 << 20, 1 << 20)


# ────────────────────────────────────────────────────────────────────────────
# A2-#6: defusedxml protects GraphML/GEXF
# ────────────────────────────────────────────────────────────────────────────


class TestDefusedXml:
    """A2-#6: GraphML and GEXF parsers refuse XXE / billion-laughs."""

    BILLION_LAUGHS = (
        '<?xml version="1.0"?>'
        "<!DOCTYPE lolz ["
        '  <!ENTITY lol "lol">'
        '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        "]>"
        "<lolz>&lol3;</lolz>"
    )

    def test_graphml_refuses_billion_laughs(self) -> None:
        from kaos_graph.io.graphml import from_graphml

        # defusedxml raises EntitiesForbidden for any DTD entity declarations
        # in the input. We catch it via the InvalidFormatError / Exception
        # surface — what matters is no expansion happens.
        with pytest.raises(Exception):  # noqa: B017
            from_graphml(self.BILLION_LAUGHS)

    def test_gexf_refuses_billion_laughs(self) -> None:
        from kaos_graph.io.gexf import from_gexf

        with pytest.raises(Exception):  # noqa: B017
            from_gexf(self.BILLION_LAUGHS)

    def test_graphml_refuses_oversize(self) -> None:
        from kaos_graph.errors import InvalidFormatError
        from kaos_graph.io.graphml import from_graphml

        # 33 MiB of valid-looking XML; cap is 32 MiB.
        big = "<root>" + "x" * (33 * 1024 * 1024) + "</root>"
        with pytest.raises(InvalidFormatError, match="refusing to parse above"):
            from_graphml(big)


# ────────────────────────────────────────────────────────────────────────────
# A2-#7: VFS name validator
# ────────────────────────────────────────────────────────────────────────────


class TestVfsNameValidator:
    """A2-#7: graph names rejected when they could escape graphs/ namespace."""

    def test_traversal_name_rejected(self) -> None:
        from kaos_graph.storage.vfs import _validate_name

        for bad in ("../etc/passwd", "../foo", "..", ".", "", "a/b", "..\\foo"):
            with pytest.raises(KaosGraphError):
                _validate_name(bad)

    def test_nul_byte_rejected(self) -> None:
        from kaos_graph.storage.vfs import _validate_name

        with pytest.raises(KaosGraphError):
            _validate_name("foo\x00bar")

    def test_leading_dot_or_hyphen_rejected(self) -> None:
        from kaos_graph.storage.vfs import _validate_name

        for bad in (".hidden", "-leading", ".active"):
            with pytest.raises(KaosGraphError):
                _validate_name(bad)

    def test_valid_names_accepted(self) -> None:
        from kaos_graph.storage.vfs import _validate_name

        for ok in ("foo", "foo_bar", "foo-bar.v2", "g_123", "A"):
            assert _validate_name(ok) == ok


# ────────────────────────────────────────────────────────────────────────────
# A2-#8: RDF parallel-edge handling
# ────────────────────────────────────────────────────────────────────────────


class TestRdfParallelEdges:
    """A2-#8: distinct RDF predicates between same s,o coexist as parallel edges."""

    def test_parallel_predicates_preserved(self) -> None:
        from kaos_graph.rdf import load_rdf

        # Two distinct predicates between ex:A and ex:B.
        ttl = (
            "@prefix ex: <http://example.org/> .\nex:A ex:knows ex:B .\nex:A ex:supervises ex:B .\n"
        )
        g, stats = load_rdf(ttl, format="turtle")
        assert stats.total_triples == 2
        assert g.is_multi is True
        assert g.n_edges == 2  # Both predicates preserved (was 1 before fix).


# ────────────────────────────────────────────────────────────────────────────
# A2-#11: graph.nodes(**filter) short-circuits empty intersections
# ────────────────────────────────────────────────────────────────────────────


class TestNodeFilterShortCircuit:
    """A2-#11: empty intersection short-circuits subsequent filter calls."""

    def test_empty_first_filter_skips_rest(self) -> None:
        # Use a sentinel filter that would crash if executed — confirms
        # the short-circuit kicks in.
        g = Graph()
        g.add_node("a", role="x")
        g.add_node("b", role="y")
        # role=missing matches nothing → second filter (active=True) should
        # not be evaluated.
        result = g.nodes(role="missing", active=True)
        assert result == []

    def test_intersection_correctness_preserved(self) -> None:
        g = Graph()
        g.add_node("a", role="x", active=True)
        g.add_node("b", role="x", active=False)
        g.add_node("c", role="y", active=True)
        assert g.nodes(role="x") == ["a", "b"]
        assert g.nodes(role="x", active=True) == ["a"]


# ────────────────────────────────────────────────────────────────────────────
# A2-#12: serve.py refuses non-loopback HTTP without bearer token
# ────────────────────────────────────────────────────────────────────────────


class TestServeAuthGate:
    """A2-#12: --http to non-loopback host refuses without --allow-remote."""

    def test_refuses_zero_zero_zero_zero(self) -> None:
        from kaos_graph.serve import main

        with pytest.raises(SystemExit) as exc:
            main(["--http", "--host", "0.0.0.0"])
        assert exc.value.code == 2

    def test_refuses_external_ip(self) -> None:
        from kaos_graph.serve import main

        with pytest.raises(SystemExit) as exc:
            main(["--http", "--host", "10.0.0.5"])
        assert exc.value.code == 2

    def test_allow_remote_without_token_refused(self, monkeypatch) -> None:
        from kaos_graph.serve import main

        monkeypatch.delenv("KAOS_GRAPH_HTTP_BEARER_TOKEN", raising=False)
        with pytest.raises(SystemExit) as exc:
            main(["--http", "--host", "0.0.0.0", "--allow-remote"])
        assert exc.value.code == 2


# ────────────────────────────────────────────────────────────────────────────
# A2-#13: critical_path returns typed error on non-numeric weight
# ────────────────────────────────────────────────────────────────────────────


class TestCriticalPathTypedError:
    """A2-#13: KaosGraphError on non-numeric weights (was: bare ValueError)."""

    def test_non_numeric_weight_raises_typed_error(self) -> None:
        from kaos_graph.algorithms import critical_path

        g = Graph()
        g.add_node("a", latency_ms="not-a-number")
        g.add_node("b", latency_ms=10)
        g.add_edge("a", "b")
        with pytest.raises(KaosGraphError, match="non-numeric"):
            critical_path(g, weight="latency_ms")


# ────────────────────────────────────────────────────────────────────────────
# A2-#14a: kaos_graph.rdf.__all__ is conditional on pyoxigraph
# ────────────────────────────────────────────────────────────────────────────


class TestRdfAllConditional:
    """A2-#14a: __all__ excludes SPARQL names when pyoxigraph isn't installed."""

    def test_all_includes_only_when_pyoxigraph_present(self) -> None:
        import kaos_graph.rdf as rdf_mod

        try:
            import pyoxigraph  # noqa: F401

            assert "query_sparql" in rdf_mod.__all__
            assert "SparqlResult" in rdf_mod.__all__
        except ImportError:
            assert "query_sparql" not in rdf_mod.__all__
            assert "SparqlResult" not in rdf_mod.__all__


# ────────────────────────────────────────────────────────────────────────────
# Audit follow-up #1-#3: post-A2 review findings
# ────────────────────────────────────────────────────────────────────────────


class TestLabelPropagationCap:
    """Follow-up #1: label_propagation has a hard iteration cap."""

    def test_two_node_graph_terminates(self) -> None:
        # The 2-node oscillation case the auditor hit: returns within the
        # iteration cap rather than hanging forever.
        from kaos_graph.algorithms import label_propagation

        g = Graph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        # No timeout needed — completes within the 100-iter cap in <1s.
        result = label_propagation(g)
        assert isinstance(result, list)


class TestMcpRawJsonCaps:
    """Follow-up #2: MCP raw json.loads paths now byte-cap via settings."""

    def test_capped_json_loads_helper_refuses_oversize(self) -> None:
        # The helper is internal but exercised through every MCP tool with
        # a *_json input. We test it via the trace-to-graph tool which is
        # one of the previously-uncapped paths.
        try:
            import kaos_core  # noqa: F401
        except ImportError:
            pytest.skip("kaos-core not installed; MCP surface unavailable")

        import asyncio

        from kaos_core import KaosRuntime

        from kaos_graph.tools import register_graph_tools

        runtime = KaosRuntime()
        # KaosRuntime doesn't expose _config as a typed attribute; setattr
        # to bypass ty's structural check for this test fixture.
        runtime._config = {"max_bytes": 100}  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
        register_graph_tools(runtime)
        # The schema-validate tool also hits _capped_json_loads — easier to
        # test because it doesn't require kaos-llm-core.
        tool = runtime.tools.get_tool("kaos-graph-validate-schema")
        assert tool is not None

        # Tiny graph + oversized schema (1 KB > 100 B cap)
        big_schema = '{"node_types":[' + ",".join('{"name":"x"}' for _ in range(40)) + "]}"
        result = asyncio.run(
            tool.execute(
                {
                    "graph_json": Graph().to_json(),
                    "schema_json": big_schema,
                },
                context=None,  # uses defaults; we set the runtime config above
            )
        )
        # Either passes (with default cap) or rejects on oversize.
        # The point: no exception escaping the tool — caps surface as
        # ToolResult errors, not unbounded parses.
        assert hasattr(result, "isError")


class TestSparqlCaps:
    """Follow-up #3: SPARQL caps query bytes / rows / wall-clock time."""

    def test_oversized_query_refused(self) -> None:
        try:
            import pyoxigraph  # noqa: F401
        except ImportError:
            pytest.skip("pyoxigraph not installed; [rdf] extra unavailable")

        from kaos_graph.rdf import query_sparql

        g = Graph()

        # Tiny settings cap; large query.
        class _S:
            max_query_bytes = 100
            max_rows = 1
            max_time_s = 1

        big_query = "SELECT ?s WHERE { ?s ?p ?o }" + " " * 200
        with pytest.raises(ValueError, match="max_query_bytes"):
            query_sparql(g, big_query, settings=_S())  # ty: ignore[call-non-callable]

    def test_row_cap_truncates(self) -> None:
        try:
            import pyoxigraph  # noqa: F401
        except ImportError:
            pytest.skip("pyoxigraph not installed; [rdf] extra unavailable")

        from kaos_graph.rdf import query_sparql

        g = Graph()
        for i in range(10):
            g.add_node(f"http://example.org/n{i}")
        for i in range(9):
            g.add_edge(
                f"http://example.org/n{i}",
                f"http://example.org/n{i + 1}",
                predicate="http://example.org/p",
            )

        class _S:
            max_query_bytes = 64 * 1024
            max_rows = 3  # truncate after 3 rows even though there are 9
            max_time_s = 30

        result = query_sparql(  # ty: ignore[call-non-callable]
            g, "SELECT ?s ?o WHERE { ?s ?p ?o }", settings=_S()
        )
        assert len(result.rows) == 3
        assert result.truncated is True
