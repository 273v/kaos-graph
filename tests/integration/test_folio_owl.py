"""Integration tests that load the FOLIO ontology.

These tests pull a multi-MiB OWL file from GitHub on first run (or read it
from ``KAOS_GRAPH_FOLIO_PATH`` if set), so they are gated behind the
``integration`` marker per audit-01 KG-002. Keeping them here — and out of
``tests/unit`` — makes ``tests/unit`` strictly hermetic and lets CI lanes
that block egress run the unit tier without spurious network failures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


class TestLoadOwlFolio:
    """KG-002 regression: FOLIO is loaded from the integration tier only."""

    def test_load_owl_folio(self, folio_owl_path: Path) -> None:
        # ``folio_owl_path`` fixture (tests/conftest.py) downloads FOLIO on
        # first use; CI hosts without network egress can set
        # ``KAOS_GRAPH_FOLIO_PATH`` to a pre-staged copy.
        from kaos_graph import Graph
        from kaos_graph.algorithms import pagerank
        from kaos_graph.rdf import load_owl

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
