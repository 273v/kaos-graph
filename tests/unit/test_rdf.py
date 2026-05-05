"""Tests for RDF/OWL loading, export, and SPARQL query."""

import json
from pathlib import Path

import pytest

from kaos_graph.rdf import RdfLoadStats, load_owl, load_rdf, to_jsonld, to_ntriples, to_turtle
from kaos_graph.rdf.sparql import SparqlResult, query_sparql, query_sparql_ask

TURTLE = """
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Animal a rdfs:Class .
ex:Dog a rdfs:Class ;
    rdfs:subClassOf ex:Animal ;
    rdfs:label "Dog" .
ex:Cat a rdfs:Class ;
    rdfs:subClassOf ex:Animal ;
    rdfs:label "Cat" .
"""


class TestLoadRdf:
    def test_load_rdf_turtle_string(self):
        g, _stats = load_rdf(TURTLE, format="turtle")
        # Should have nodes for the subjects/objects: ex:Animal, ex:Dog, ex:Cat, rdfs:Class
        assert g.n_nodes > 0
        assert g.n_edges > 0
        # Sanity: at least 3 entities (Animal, Dog, Cat)
        assert g.n_nodes >= 3

    def test_load_rdf_stats(self):
        _, stats = load_rdf(TURTLE, format="turtle")
        assert isinstance(stats, RdfLoadStats)
        assert stats.total_triples > 0
        assert stats.nodes > 0
        assert stats.edges > 0
        assert stats.load_time_ms >= 0
        # literal_properties should account for the rdfs:label triples
        assert stats.literal_properties >= 0


class TestLoadOwl:
    def test_load_owl_folio(self, folio_owl_path: Path) -> None:
        # ``folio_owl_path`` fixture (tests/conftest.py) downloads FOLIO on
        # first use; CI hosts without network egress can set
        # ``KAOS_GRAPH_FOLIO_PATH`` to a pre-staged copy.
        from kaos_graph import Graph
        from kaos_graph.algorithms import pagerank

        g, stats = load_owl(folio_owl_path)
        assert g.n_nodes > 1000
        assert stats.total_triples > 0

        # Run pagerank on the ontology graph
        ranks = pagerank(g)
        assert len(ranks) > 0
        assert ranks[0].score > 0

        # JSON round-trip — large graph; raise the cap above default 64 MiB
        # so to_json/from_json passes for FOLIO's ~25K nodes.
        class _S:
            max_bytes = 1 << 30  # 1 GiB
            max_nodes = 1_000_000
            max_edges = 10_000_000

        json_str = g.to_json()
        g2 = Graph.from_json(json_str, settings=_S())
        assert g2.n_nodes == g.n_nodes
        assert g2.n_edges == g.n_edges


class TestExportTurtle:
    def test_export_turtle(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        turtle = to_turtle(g)

        # Should contain the expected IRIs
        assert "http://example.org/Dog" in turtle or "example.org/Dog" in turtle
        assert "http://example.org/Animal" in turtle or "example.org/Animal" in turtle
        # Should contain a predicate (subClassOf or type)
        assert "subClassOf" in turtle or "rdf-schema" in turtle

    def test_turtle_roundtrip(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        turtle = to_turtle(g)
        g2, _ = load_rdf(turtle, format="turtle")

        assert g2.n_nodes == g.n_nodes
        assert g2.n_edges == g.n_edges


class TestExportNTriples:
    def test_export_ntriples(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        nt = to_ntriples(g)

        # N-Triples uses full IRIs in angle brackets
        assert "<http://example.org/Dog>" in nt
        assert "<http://example.org/Animal>" in nt
        # Each non-empty line ends with " ."
        for line in nt.strip().splitlines():
            line = line.strip()
            if line:
                assert line.endswith(" ."), f"Expected line to end with ' .': {line}"

    def test_ntriples_roundtrip(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        nt = to_ntriples(g)
        g2, _ = load_rdf(nt, format="ntriples")

        assert g2.n_nodes == g.n_nodes
        assert g2.n_edges == g.n_edges


class TestSparql:
    """SPARQL query tests using pyoxigraph."""

    def test_sparql_basic(self):
        """Basic SPARQL SELECT over an RDF-loaded graph."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql(g, "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5")
        assert isinstance(result, SparqlResult)
        assert len(result.rows) > 0
        assert "s" in result.rows[0]
        assert "p" in result.rows[0]
        assert "o" in result.rows[0]

    def test_sparql_variables(self):
        """Variable names are returned correctly."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql(g, "SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
        assert result.variables == ["s", "p", "o"]

    def test_sparql_specific_pattern(self):
        """Query for a specific triple pattern."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql(
            g,
            """
            SELECT ?subclass WHERE {
                ?subclass <http://www.w3.org/2000/01/rdf-schema#subClassOf>
                          <http://example.org/Animal> .
            }
            """,
        )
        # Dog and Cat are subClassOf Animal
        subclasses = {row["subclass"] for row in result.rows}
        assert "http://example.org/Dog" in subclasses
        assert "http://example.org/Cat" in subclasses

    def test_sparql_ask_true(self):
        """ASK query returns True when pattern matches."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql_ask(g, "ASK { ?s ?p ?o }")
        assert result is True

    def test_sparql_ask_false(self):
        """ASK query returns False when pattern does not match."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql_ask(
            g,
            "ASK { <http://example.org/Unicorn> ?p ?o }",
        )
        assert result is False

    def test_sparql_count(self):
        """COUNT aggregate in SPARQL."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql(g, "SELECT (COUNT(*) AS ?cnt) WHERE { ?s ?p ?o }")
        assert len(result.rows) == 1
        count = int(result.rows[0]["cnt"])
        assert count > 0

    def test_sparql_empty_result(self):
        """Query with no matches returns empty rows."""
        g, _ = load_rdf(TURTLE, format="turtle")
        result = query_sparql(
            g,
            "SELECT ?s WHERE { <http://nonexistent/> ?p ?s }",
        )
        assert len(result.rows) == 0
        assert result.variables == ["s"]

    def test_sparql_invalid_query(self):
        """Invalid SPARQL raises ValueError."""
        g, _ = load_rdf(TURTLE, format="turtle")
        with pytest.raises(ValueError, match="Invalid SPARQL"):
            query_sparql(g, "THIS IS NOT SPARQL")

    def test_sparql_on_property_graph(self):
        """SPARQL works on a plain property graph (non-RDF source)."""
        from kaos_graph.graph import Graph

        g = Graph(directed=True)
        g.add_node("http://example.org/A")
        g.add_node("http://example.org/B")
        g.add_edge(
            "http://example.org/A",
            "http://example.org/B",
            predicate="http://example.org/knows",
        )

        result = query_sparql(g, "SELECT ?s ?o WHERE { ?s <http://example.org/knows> ?o }")
        assert len(result.rows) == 1
        assert result.rows[0]["s"] == "http://example.org/A"
        assert result.rows[0]["o"] == "http://example.org/B"


class TestExportJsonLd:
    def test_basic(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        jsonld = to_jsonld(g)
        parsed = json.loads(jsonld)
        assert "@graph" in parsed
        graph_arr = parsed["@graph"]
        assert len(graph_arr) > 0
        # Every entry should have @id
        for entry in graph_arr:
            assert "@id" in entry

    def test_contains_expected_iris(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        jsonld = to_jsonld(g)
        assert "http://example.org/Dog" in jsonld
        assert "http://example.org/Animal" in jsonld

    def test_empty_graph(self):
        from kaos_graph.graph import Graph

        g = Graph(directed=True)
        jsonld = to_jsonld(g)
        parsed = json.loads(jsonld)
        assert parsed["@graph"] == []

    def test_valid_json(self):
        g, _ = load_rdf(TURTLE, format="turtle")
        jsonld = to_jsonld(g)
        # Should be valid JSON
        parsed = json.loads(jsonld)
        assert isinstance(parsed, dict)
