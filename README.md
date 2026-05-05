# kaos-graph

High-performance graph library for the Kelvin Agentic OS.

Backed by [petgraph](https://github.com/petgraph/petgraph) (Rust) with PyO3 bindings.

## Features

- String-keyed nodes with JSON-compatible properties
- Directed, undirected, and optional multigraph semantics
- Built-in algorithms: BFS/DFS, Dijkstra, Bellman-Ford, A*, PageRank, Tarjan SCC, topological sort, critical path, matching, cliques, bridges
- JSON serialization and pickle support
- Typed Python API with dataclass result types
- Program/trace graph helpers for kaos-llm-core integration

## Quick Start

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

## Program And Trace Graphs

```python
from kaos_graph.algorithms import critical_path
from kaos_graph.programs import program_to_graph, trace_to_graph

structure = program_to_graph(my_program)
runtime = trace_to_graph(my_trace)

# Static containment view of a Program
print(structure.to_json())

# Runtime bottleneck analysis over an ExecutionTrace
bottleneck = critical_path(runtime, weight="latency_ms")
print(bottleneck.path, bottleneck.cost)
```

`program_to_graph()` produces a containment graph from `Program.named_calls()`. `trace_to_graph()` produces a runtime execution graph with `data_flow` edges plus timing and cost metadata for critical-path analysis.
