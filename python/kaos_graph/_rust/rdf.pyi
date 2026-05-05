"""Type stubs for kaos_graph._rust.rdf."""

from typing import Any

from kaos_graph._rust.graph import PyGraph

def load_rdf_file(
    path: str,
    max_bytes: int,
    triple_cap: int,
) -> tuple[PyGraph, dict[str, Any]]: ...
def load_rdf_string(
    data: str,
    format: str,
    max_bytes: int,
    triple_cap: int,
) -> tuple[PyGraph, dict[str, Any]]: ...
def export_turtle(graph: PyGraph) -> str: ...
def export_ntriples(graph: PyGraph) -> str: ...
def export_jsonld(graph: PyGraph) -> str: ...
