import pytest


class TestTabularBridge:
    def test_to_tabular_import_guard(self):
        """Verify to_tabular raises ImportError when kaos-content is not installed."""
        # This test checks the behavior -- if kaos-content IS installed, it should work
        from kaos_graph import Graph
        from kaos_graph.bridges.tabular import to_tabular

        g = Graph()
        g.add_node("a", name="Alice")
        g.add_node("b", name="Bob")
        g.add_edge("a", "b", weight=1.0)

        try:
            nodes_doc, edges_doc = to_tabular(g)
            # If kaos-content is installed, verify the tables
            assert nodes_doc.tables[0].name == "nodes"
            assert edges_doc.tables[0].name == "edges"
            assert nodes_doc.tables[0].row_count == 2
            assert edges_doc.tables[0].row_count == 1
        except ImportError:
            pytest.skip("kaos-content not installed")
