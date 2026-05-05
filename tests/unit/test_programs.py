"""Tests for kaos-graph program_to_graph conversion."""

from __future__ import annotations

import pytest

from kaos_graph import Graph


class TestProgramToGraphImport:
    """Test that program_to_graph is importable and raises correctly."""

    def test_importable(self) -> None:
        """program_to_graph is importable from kaos_graph.programs."""
        from kaos_graph.programs import program_to_graph

        assert callable(program_to_graph)

    def test_raises_without_llm_core(self) -> None:
        """program_to_graph raises ImportError without kaos-llm-core."""
        from kaos_graph.programs import program_to_graph

        # A plain object is not a Program, but the ImportError check happens
        # before the isinstance check only if kaos-llm-core is not installed.
        try:
            from kaos_llm_core.programs.base import Program  # noqa: F401
        except ImportError:
            with pytest.raises(ImportError, match="kaos-llm-core is required"):
                program_to_graph(object())
            return

        # If kaos-llm-core IS installed, we get TypeError instead
        with pytest.raises(TypeError, match="Expected a Program"):
            program_to_graph(object())

    def test_rejects_non_program(self) -> None:
        """program_to_graph raises TypeError for non-Program objects."""
        try:
            from kaos_llm_core.programs.base import Program  # noqa: F401
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_graph.programs import program_to_graph

        with pytest.raises(TypeError, match="Expected a Program"):
            program_to_graph("not a program")

        with pytest.raises(TypeError, match="Expected a Program"):
            program_to_graph(42)


class TestProgramToGraphConversion:
    """Test program_to_graph with real Program objects (requires kaos-llm-core)."""

    def test_simple_program(self) -> None:
        """Convert a simple Program with two Calls."""
        try:
            from kaos_llm_core.programs.base import Program
            from kaos_llm_core.programs.call import Call
            from kaos_llm_core.signatures.signature import Signature
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_llm_core.signatures.fields import InputField, OutputField

        from kaos_graph.programs import program_to_graph

        class DummyInput(Signature):
            """Dummy signature for testing."""

            text: str = InputField(description="Input text")
            result: str = OutputField(description="Output result")

        class SimpleProgram(Program):
            def __init__(self) -> None:
                self.step_a = Call(DummyInput, model="openai:gpt-4o-mini")
                self.step_b = Call(DummyInput, model="openai:gpt-4o-mini")

        prog = SimpleProgram()
        g = program_to_graph(prog)

        assert isinstance(g, Graph)
        assert g.is_directed
        assert g.name == "SimpleProgram"

        # Root + 2 calls = 3 nodes
        assert g.n_nodes == 3
        assert g.has_node("__program__")
        assert g.has_node("step_a")
        assert g.has_node("step_b")

        # Root connects to both calls
        assert g.has_edge("__program__", "step_a")
        assert g.has_edge("__program__", "step_b")

        # It is a DAG
        assert g.is_dag()

        # Node properties
        root_props = g.node("__program__")
        assert root_props is not None
        assert root_props["type"] == "program"
        assert root_props["class_name"] == "SimpleProgram"

        call_props = g.node("step_a")
        assert call_props is not None
        assert call_props["type"] == "call"
        assert call_props["class_name"] == "Call"

    def test_nested_program(self) -> None:
        """Convert a nested Program (Program containing a sub-Program)."""
        try:
            from kaos_llm_core.programs.base import Program
            from kaos_llm_core.programs.call import Call
            from kaos_llm_core.signatures.signature import Signature
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_llm_core.signatures.fields import InputField, OutputField

        from kaos_graph.programs import program_to_graph

        class DummySig(Signature):
            """Dummy signature."""

            text: str = InputField(description="Input text")
            result: str = OutputField(description="Output result")

        class InnerProgram(Program):
            def __init__(self) -> None:
                self.inner_call = Call(DummySig, model="openai:gpt-4o-mini")

        class OuterProgram(Program):
            def __init__(self) -> None:
                self.sub = InnerProgram()
                self.direct_call = Call(DummySig, model="openai:gpt-4o-mini")

        prog = OuterProgram()
        g = program_to_graph(prog)

        assert isinstance(g, Graph)
        assert g.has_node("__program__")
        assert g.has_node("sub")
        assert g.has_node("direct_call")
        # Sub-program's call gets prefixed
        assert g.has_node("sub.inner_call")
        # Containment edges
        assert g.has_edge("__program__", "sub")
        assert g.has_edge("__program__", "direct_call")
        assert g.has_edge("sub", "sub.inner_call")

        # Node types
        sub_props = g.node("sub")
        assert sub_props is not None
        assert sub_props["type"] == "program"
        dc_props = g.node("direct_call")
        assert dc_props is not None
        assert dc_props["type"] == "call"
        si_props = g.node("sub.inner_call")
        assert si_props is not None
        assert si_props["type"] == "call"

    def test_empty_program(self) -> None:
        """Convert a Program with no calls."""
        try:
            from kaos_llm_core.programs.base import Program
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_graph.programs import program_to_graph

        class EmptyProgram(Program):
            pass

        g = program_to_graph(EmptyProgram())
        assert g.n_nodes == 1  # Just __program__
        assert g.n_edges == 0
        assert g.has_node("__program__")

    def test_deeply_nested_program(self) -> None:
        """Convert a 3-level nested Program (root -> mid -> leaf calls)."""
        try:
            from kaos_llm_core.programs.base import Program
            from kaos_llm_core.programs.call import Call
            from kaos_llm_core.signatures.fields import InputField, OutputField
            from kaos_llm_core.signatures.signature import Signature
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_graph.programs import program_to_graph

        class DummySig(Signature):
            """Dummy signature."""

            text: str = InputField(description="Input text")
            result: str = OutputField(description="Output result")

        class LeafProgram(Program):
            def __init__(self) -> None:
                self.leaf_call = Call(DummySig, model="openai:gpt-4o-mini")

        class MidProgram(Program):
            def __init__(self) -> None:
                self.mid_call = Call(DummySig, model="openai:gpt-4o-mini")
                self.leaf = LeafProgram()

        class RootProgram(Program):
            def __init__(self) -> None:
                self.top_call = Call(DummySig, model="openai:gpt-4o-mini")
                self.mid = MidProgram()

        prog = RootProgram()
        g = program_to_graph(prog)

        assert isinstance(g, Graph)
        assert g.is_directed

        # Root + top_call + mid + mid.mid_call + mid.leaf + mid.leaf.leaf_call = 6 nodes
        assert g.n_nodes == 6
        assert g.has_node("__program__")
        assert g.has_node("top_call")
        assert g.has_node("mid")
        assert g.has_node("mid.mid_call")
        assert g.has_node("mid.leaf")
        assert g.has_node("mid.leaf.leaf_call")

        # Containment edges at all levels
        assert g.has_edge("__program__", "top_call")
        assert g.has_edge("__program__", "mid")
        assert g.has_edge("mid", "mid.mid_call")
        assert g.has_edge("mid", "mid.leaf")
        assert g.has_edge("mid.leaf", "mid.leaf.leaf_call")

        # Node types
        mid_props = g.node("mid")
        leaf_props = g.node("mid.leaf")
        leaf_call_props = g.node("mid.leaf.leaf_call")
        mid_call_props = g.node("mid.mid_call")
        assert mid_props is not None
        assert leaf_props is not None
        assert leaf_call_props is not None
        assert mid_call_props is not None
        assert mid_props["type"] == "program"
        assert leaf_props["type"] == "program"
        assert leaf_call_props["type"] == "call"
        assert mid_call_props["type"] == "call"

        assert g.is_dag()


class TestTraceToGraph:
    def test_trace_to_graph_basic(self) -> None:
        """Convert a simple ExecutionTrace with two children to a data-flow graph."""
        try:
            from kaos_llm_core.observability.traces import ExecutionTrace
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_graph.programs import trace_to_graph

        trace = ExecutionTrace(
            call_name="pipeline",
            latency_ms=500.0,
            children=[
                ExecutionTrace(
                    call_name="extract",
                    latency_ms=200.0,
                    model="openai:gpt-4o-mini",
                    input_tokens=100,
                    output_tokens=50,
                ),
                ExecutionTrace(
                    call_name="summarize",
                    latency_ms=300.0,
                    model="openai:gpt-4o-mini",
                    input_tokens=200,
                    output_tokens=100,
                ),
            ],
        )

        g = trace_to_graph(trace)
        assert isinstance(g, Graph)
        assert g.is_directed
        assert g.is_dag()

        # Root + 2 children = 3 nodes
        assert g.n_nodes == 3

        # Containment edges: pipeline → extract, pipeline → summarize
        assert g.has_node("pipeline")
        assert g.has_node("pipeline.extract")
        assert g.has_node("pipeline.summarize")

        # Data-flow edge: extract → summarize (sequential)
        data_flow_edges = g.edges(type="data_flow")
        assert len(data_flow_edges) == 1
        assert data_flow_edges[0].source == "pipeline.extract"
        assert data_flow_edges[0].target == "pipeline.summarize"

        # Node properties include timing
        extract = g.node("pipeline.extract")
        assert extract is not None
        assert extract["latency_ms"] == 200.0
        assert extract["model"] == "openai:gpt-4o-mini"

    def test_trace_to_graph_critical_path(self) -> None:
        """critical_path() finds the bottleneck in a trace graph."""
        try:
            from kaos_llm_core.observability.traces import ExecutionTrace
        except ImportError:
            pytest.skip("kaos-llm-core not installed")

        from kaos_graph.algorithms import critical_path
        from kaos_graph.programs import trace_to_graph

        trace = ExecutionTrace(
            call_name="pipeline",
            latency_ms=0.0,
            children=[
                ExecutionTrace(call_name="fast_step", latency_ms=50.0),
                ExecutionTrace(call_name="slow_step", latency_ms=500.0),
                ExecutionTrace(call_name="medium_step", latency_ms=100.0),
            ],
        )

        g = trace_to_graph(trace)
        result = critical_path(g, weight="latency_ms")

        assert result.cost >= 500.0
        assert "pipeline.slow_step" in result.path
