"""LLM-program / trace MCP tools.

Tools registered here:

- ``kaos-graph-trace-to-graph`` — convert a kaos-llm-core ExecutionTrace into
  a data-flow graph. Requires the ``programs`` extra (kaos-llm-core).
"""

from __future__ import annotations

import json
from typing import Any

from kaos_graph.tools._common import _MODULE, _VERSION, get_logger, readonly_annotations

__all__ = ["register_program_tools"]

logger = get_logger()


def register_program_tools(runtime: Any) -> int:
    """Register the program/trace-conversion tools with ``runtime``."""
    from kaos_core.base.context import KaosContext
    from kaos_core.base.tool import KaosTool
    from kaos_core.types.enums import ToolCapability, ToolCategory
    from kaos_core.types.metadata import ToolMetadata
    from kaos_core.types.parameters import ParameterSchema
    from kaos_core.types.results import ToolResult

    _READONLY = readonly_annotations()

    # ── kaos-graph-trace-to-graph ────────────────────────────────────

    class TraceToGraphTool(KaosTool):
        @property
        def metadata(self) -> ToolMetadata:
            return ToolMetadata(
                name="kaos-graph-trace-to-graph",
                display_name="Trace to Graph",
                description=(
                    "Convert a kaos-llm-core ExecutionTrace to a data-flow graph "
                    "with timing and cost properties on each node. "
                    "The resulting DAG supports critical_path analysis via "
                    "kaos-graph-critical-path. "
                    "Requires the 'programs' extra (kaos-llm-core)."
                ),
                category=ToolCategory.DATA,
                capability=ToolCapability.TRANSFORM,
                module_name=_MODULE,
                version=_VERSION,
                annotations=_READONLY,
                input_schema=[
                    ParameterSchema(
                        name="trace_json",
                        type="string",
                        description=(
                            "JSON-serialized ExecutionTrace from kaos-llm-core. "
                            "Must include call_name, trace_id, children, "
                            "latency_ms, cost_usd, and token counts."
                        ),
                    ),
                ],
            )

        async def execute(
            self, inputs: dict[str, Any], context: KaosContext | None = None
        ) -> ToolResult:
            try:
                from kaos_llm_core.observability.traces import ExecutionTrace
            except ImportError:
                return ToolResult.create_error(
                    "kaos-llm-core is required for trace_to_graph. "
                    "Install with: pip install kaos-graph[programs]"
                )

            try:
                from kaos_graph.programs.convert import trace_to_graph

                trace_data = json.loads(inputs["trace_json"])
                trace = ExecutionTrace(**trace_data)
                g = trace_to_graph(trace)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                return ToolResult.create_error(
                    f"Failed to parse trace JSON: {exc}. "
                    "Provide a valid ExecutionTrace JSON object."
                )
            except Exception as exc:
                logger.debug("Failed to convert trace to graph: %s", exc)
                return ToolResult.create_error(
                    f"Failed to convert trace to graph: {exc}. "
                    "Ensure the trace JSON has the expected ExecutionTrace structure "
                    "(call_name, trace_id, children, latency_ms, cost_usd, token counts). "
                    "Obtain a valid trace from kaos-llm-core's observability module."
                )

            info = {
                "n_nodes": g.n_nodes,
                "n_edges": g.n_edges,
                "graph_data": g.to_json(),
            }
            summary = f"Converted trace to graph: {g.n_nodes} nodes, {g.n_edges} edges."
            return ToolResult.create_success(info, summary=summary)

    runtime.tools.register_tool(TraceToGraphTool())
    return 1
