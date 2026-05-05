//! RDF/OWL loading via oxrdf/oxrdfio. Parses RDF files directly in Rust
//! and builds a kaos-graph Graph from the triples. No RocksDB, no database —
//! just the parser.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use oxrdf::Term;
use oxrdfio::{RdfFormat, RdfParser, RdfSerializer};
use serde_json::Value;

use super::graph::Graph;

/// Statistics from an RDF load operation.
#[derive(Debug, Clone)]
pub struct RdfLoadStats {
    pub total_triples: usize,
    pub nodes: usize,
    pub edges: usize,
    pub literal_properties: usize,
    pub load_time_ms: u128,
}

/// Shorten an IRI to a readable label.
fn shorten_iri(iri: &str) -> String {
    if let Some(pos) = iri.rfind('#') {
        iri[pos + 1..].to_string()
    } else if let Some(pos) = iri.rfind('/') {
        iri[pos + 1..].to_string()
    } else {
        iri.to_string()
    }
}

/// Detect RDF format from file extension. Returns ``None`` for unknown
/// extensions so callers can refuse rather than silently fall through to
/// RDF/XML (audit A2-#5).
fn detect_format(path: &Path) -> Option<RdfFormat> {
    match path.extension().and_then(|e| e.to_str()) {
        Some("ttl") => Some(RdfFormat::Turtle),
        Some("nt") => Some(RdfFormat::NTriples),
        Some("nq") => Some(RdfFormat::NQuads),
        Some("trig") => Some(RdfFormat::TriG),
        Some("rdf") | Some("owl") => Some(RdfFormat::RdfXml),
        _ => None,
    }
}

/// Load an RDF file (OWL/TTL/RDF-XML/N-Triples) into a Graph.
///
/// Each unique IRI becomes a node. Each triple where both subject and object
/// are IRIs becomes an edge. Literal counts are tracked in stats.
///
/// Refuses unknown file extensions (callers must pass an explicit format
/// via :func:`load_rdf_file_with_format` instead). Refuses files larger than
/// ``max_bytes`` (audit A2-#3, A2-#5). ``triple_cap`` aborts mid-parse if a
/// document tries to materialize more than the cap.
pub fn load_rdf_file_capped(
    path: &str,
    max_bytes: u64,
    triple_cap: usize,
) -> Result<(Graph, RdfLoadStats), String> {
    let filepath = Path::new(path);
    let format = detect_format(filepath).ok_or_else(|| {
        format!(
            "Unknown RDF file extension for {:?}; pass an explicit format \
             (turtle/ntriples/rdfxml/nquads/trig) via load_rdf_string instead.",
            filepath.extension().and_then(|e| e.to_str()).unwrap_or("")
        )
    })?;

    let metadata =
        std::fs::metadata(filepath).map_err(|e| format!("Failed to stat file: {}", e))?;
    if metadata.len() > max_bytes {
        return Err(format!(
            "RDF file is {} bytes; refusing to load above {} bytes \
             (raise KaosGraphSettings.max_bytes if intended).",
            metadata.len(),
            max_bytes
        ));
    }

    let start = std::time::Instant::now();
    let file = std::fs::File::open(filepath).map_err(|e| format!("Failed to open file: {}", e))?;
    let reader = std::io::BufReader::new(file);

    let parser = RdfParser::from_format(format);
    // A2-#8: RDF naturally has parallel predicates between the same s,o
    // (e.g. ex:Dog rdf:type rdfs:Class AND ex:Dog dc:subject rdfs:Class).
    // Build a multi-graph so distinct predicates aren't silently coalesced.
    let mut graph = Graph::new_multi(true, true);
    let mut total_triples = 0usize;
    let mut literal_properties = 0usize;

    for result in parser.for_reader(reader) {
        let quad = result.map_err(|e| format!("Parse error: {}", e))?;
        total_triples += 1;
        if total_triples > triple_cap {
            return Err(format!(
                "RDF parse exceeded triple_cap={} (raise KaosGraphSettings.max_triples if intended).",
                triple_cap
            ));
        }

        // Subject → node
        let subj_iri = match &quad.subject {
            oxrdf::NamedOrBlankNode::NamedNode(n) => n.as_str().to_string(),
            oxrdf::NamedOrBlankNode::BlankNode(b) => format!("_:{}", b.as_str()),
        };

        if !graph.has_node(&subj_iri) {
            let mut props = HashMap::new();
            props.insert("label".to_string(), Value::String(shorten_iri(&subj_iri)));
            graph.add_node(&subj_iri, props).ok();
        }

        let pred_iri = quad.predicate.as_str().to_string();
        let pred_label = shorten_iri(&pred_iri);

        match &quad.object {
            Term::NamedNode(obj) => {
                let obj_iri = obj.as_str().to_string();
                if !graph.has_node(&obj_iri) {
                    let mut props = HashMap::new();
                    props.insert("label".to_string(), Value::String(shorten_iri(&obj_iri)));
                    graph.add_node(&obj_iri, props).ok();
                }
                let mut edge_props = HashMap::new();
                edge_props.insert("predicate".to_string(), Value::String(pred_iri));
                edge_props.insert("label".to_string(), Value::String(pred_label.clone()));
                edge_props.insert("type".to_string(), Value::String(pred_label));
                // A2-#8: with multi=true above, this only errors if a node
                // is missing — propagate rather than swallow so future
                // refactors that violate the invariant fail loudly.
                graph
                    .add_edge(&subj_iri, &obj_iri, edge_props)
                    .map_err(|e| format!("Failed to add RDF edge: {}", e))?;
            }
            Term::Literal(_) => {
                literal_properties += 1;
            }
            Term::BlankNode(b) => {
                let obj_iri = format!("_:{}", b.as_str());
                if !graph.has_node(&obj_iri) {
                    let mut props = HashMap::new();
                    props.insert("label".to_string(), Value::String(obj_iri.clone()));
                    graph.add_node(&obj_iri, props).ok();
                }
                let mut edge_props = HashMap::new();
                edge_props.insert("predicate".to_string(), Value::String(pred_iri));
                edge_props.insert("label".to_string(), Value::String(pred_label.clone()));
                edge_props.insert("type".to_string(), Value::String(pred_label));
                // A2-#8: with multi=true above, this only errors if a node
                // is missing — propagate rather than swallow so future
                // refactors that violate the invariant fail loudly.
                graph
                    .add_edge(&subj_iri, &obj_iri, edge_props)
                    .map_err(|e| format!("Failed to add RDF edge: {}", e))?;
            }
        }
    }

    let load_time_ms = start.elapsed().as_millis();
    let stats = RdfLoadStats {
        total_triples,
        nodes: graph.n_nodes(),
        edges: graph.n_edges(),
        literal_properties,
        load_time_ms,
    };

    Ok((graph, stats))
}

/// Back-compat: load an RDF file with no caps. Internal callers and tests
/// only — the PyO3 boundary always uses :func:`load_rdf_file_capped` with
/// settings-derived limits (audit A2-#3).
pub fn load_rdf_file(path: &str) -> Result<(Graph, RdfLoadStats), String> {
    load_rdf_file_capped(path, u64::MAX, usize::MAX)
}

/// Load RDF from a string with explicit caps (audit A2-#3, A2-#5).
pub fn load_rdf_string_capped(
    data: &str,
    format: RdfFormat,
    max_bytes: usize,
    triple_cap: usize,
) -> Result<(Graph, RdfLoadStats), String> {
    if data.len() > max_bytes {
        return Err(format!(
            "RDF string is {} bytes; refusing to parse above {} bytes \
             (raise KaosGraphSettings.max_bytes if intended).",
            data.len(),
            max_bytes
        ));
    }
    let start = std::time::Instant::now();
    let parser = RdfParser::from_format(format);
    // A2-#8: RDF naturally has parallel predicates between the same s,o
    // (e.g. ex:Dog rdf:type rdfs:Class AND ex:Dog dc:subject rdfs:Class).
    // Build a multi-graph so distinct predicates aren't silently coalesced.
    let mut graph = Graph::new_multi(true, true);
    let mut total_triples = 0usize;
    let mut literal_properties = 0usize;

    for result in parser.for_reader(data.as_bytes()) {
        let quad = result.map_err(|e| format!("Parse error: {}", e))?;
        total_triples += 1;
        if total_triples > triple_cap {
            return Err(format!(
                "RDF parse exceeded triple_cap={} (raise KaosGraphSettings.max_triples if intended).",
                triple_cap
            ));
        }

        let subj_iri = match &quad.subject {
            oxrdf::NamedOrBlankNode::NamedNode(n) => n.as_str().to_string(),
            oxrdf::NamedOrBlankNode::BlankNode(b) => format!("_:{}", b.as_str()),
        };

        if !graph.has_node(&subj_iri) {
            let mut props = HashMap::new();
            props.insert("label".to_string(), Value::String(shorten_iri(&subj_iri)));
            graph.add_node(&subj_iri, props).ok();
        }

        let pred_iri = quad.predicate.as_str().to_string();
        let pred_label = shorten_iri(&pred_iri);

        match &quad.object {
            Term::NamedNode(obj) => {
                let obj_iri = obj.as_str().to_string();
                if !graph.has_node(&obj_iri) {
                    let mut props = HashMap::new();
                    props.insert("label".to_string(), Value::String(shorten_iri(&obj_iri)));
                    graph.add_node(&obj_iri, props).ok();
                }
                let mut edge_props = HashMap::new();
                edge_props.insert("predicate".to_string(), Value::String(pred_iri));
                edge_props.insert("label".to_string(), Value::String(pred_label.clone()));
                edge_props.insert("type".to_string(), Value::String(pred_label));
                // A2-#8: with multi=true above, this only errors if a node
                // is missing — propagate rather than swallow so future
                // refactors that violate the invariant fail loudly.
                graph
                    .add_edge(&subj_iri, &obj_iri, edge_props)
                    .map_err(|e| format!("Failed to add RDF edge: {}", e))?;
            }
            Term::Literal(_) => {
                literal_properties += 1;
            }
            Term::BlankNode(b) => {
                let obj_iri = format!("_:{}", b.as_str());
                if !graph.has_node(&obj_iri) {
                    let mut props = HashMap::new();
                    props.insert("label".to_string(), Value::String(obj_iri.clone()));
                    graph.add_node(&obj_iri, props).ok();
                }
                let mut edge_props = HashMap::new();
                edge_props.insert("predicate".to_string(), Value::String(pred_iri));
                edge_props.insert("label".to_string(), Value::String(pred_label.clone()));
                edge_props.insert("type".to_string(), Value::String(pred_label));
                // A2-#8: with multi=true above, this only errors if a node
                // is missing — propagate rather than swallow so future
                // refactors that violate the invariant fail loudly.
                graph
                    .add_edge(&subj_iri, &obj_iri, edge_props)
                    .map_err(|e| format!("Failed to add RDF edge: {}", e))?;
            }
        }
    }

    let load_time_ms = start.elapsed().as_millis();
    let stats = RdfLoadStats {
        total_triples,
        nodes: graph.n_nodes(),
        edges: graph.n_edges(),
        literal_properties,
        load_time_ms,
    };
    Ok((graph, stats))
}

/// Back-compat: load RDF from a string with no caps. Internal callers and
/// tests only — the PyO3 boundary always uses :func:`load_rdf_string_capped`.
pub fn load_rdf_string(data: &str, format: RdfFormat) -> Result<(Graph, RdfLoadStats), String> {
    load_rdf_string_capped(data, format, usize::MAX, usize::MAX)
}

/// Default predicate IRI used when an edge has no `predicate` property.
const DEFAULT_PREDICATE: &str = "http://kaos.273v.com/graph#relatedTo";

/// Internal helper: serialize a Graph to an RDF format string.
fn export_rdf(graph: &Graph, format: RdfFormat) -> Result<String, String> {
    let mut writer = RdfSerializer::from_format(format).for_writer(Vec::new());

    for (src_id, tgt_id, edge_data) in graph.edges_vec() {
        // Determine predicate IRI from edge properties: "predicate" first, then "type",
        // then fall back to default.
        let pred_iri = edge_data
            .properties
            .get("predicate")
            .and_then(|v| v.as_str())
            .or_else(|| edge_data.properties.get("type").and_then(|v| v.as_str()))
            .unwrap_or(DEFAULT_PREDICATE);

        let predicate = oxrdf::NamedNodeRef::new(pred_iri)
            .map_err(|e| format!("Invalid predicate IRI '{}': {}", pred_iri, e))?;

        // Build subject: BlankNode if starts with "_:", else NamedNode.
        let subject: oxrdf::NamedOrBlankNodeRef<'_> =
            if let Some(bnode_id) = src_id.strip_prefix("_:") {
                oxrdf::BlankNodeRef::new(bnode_id)
                    .map_err(|e| format!("Invalid blank node id '{}': {}", src_id, e))?
                    .into()
            } else {
                oxrdf::NamedNodeRef::new(src_id)
                    .map_err(|e| format!("Invalid subject IRI '{}': {}", src_id, e))?
                    .into()
            };

        // Build object: BlankNode if starts with "_:", else NamedNode.
        let object: oxrdf::TermRef<'_> = if let Some(bnode_id) = tgt_id.strip_prefix("_:") {
            oxrdf::BlankNodeRef::new(bnode_id)
                .map_err(|e| format!("Invalid blank node id '{}': {}", tgt_id, e))?
                .into()
        } else {
            oxrdf::NamedNodeRef::new(tgt_id)
                .map_err(|e| format!("Invalid object IRI '{}': {}", tgt_id, e))?
                .into()
        };

        writer
            .serialize_triple(oxrdf::TripleRef::new(subject, predicate, object))
            .map_err(|e| format!("Serialization error: {}", e))?;
    }

    let bytes = writer
        .finish()
        .map_err(|e| format!("Finish error: {}", e))?;
    String::from_utf8(bytes).map_err(|e| format!("UTF-8 error: {}", e))
}

/// Export a Graph to Turtle format string.
pub fn export_turtle(graph: &Graph) -> Result<String, String> {
    export_rdf(graph, RdfFormat::Turtle)
}

/// Export a Graph to N-Triples format string.
pub fn export_ntriples(graph: &Graph) -> Result<String, String> {
    export_rdf(graph, RdfFormat::NTriples)
}

/// Export a Graph to JSON-LD format string.
///
/// Since oxrdfio 0.2 does not include a JSON-LD serializer, we build the
/// JSON-LD structure manually.  Each edge becomes an entry in the `@graph`
/// array; subjects are grouped so that all predicates for the same subject
/// appear together.
pub fn export_jsonld(graph: &Graph) -> Result<String, String> {
    use std::collections::BTreeMap;

    // Group edges by subject: subject -> [(predicate, object)]
    let mut subject_map: BTreeMap<&str, Vec<(&str, &str)>> = BTreeMap::new();

    for (src_id, tgt_id, edge_data) in graph.edges_vec() {
        let pred_iri = edge_data
            .properties
            .get("predicate")
            .and_then(|v| v.as_str())
            .or_else(|| edge_data.properties.get("type").and_then(|v| v.as_str()))
            .unwrap_or(DEFAULT_PREDICATE);

        subject_map
            .entry(src_id)
            .or_default()
            .push((pred_iri, tgt_id));
    }

    // Build JSON-LD @graph array
    let mut graph_nodes = Vec::new();
    for (subj, pred_objects) in &subject_map {
        let mut node = serde_json::Map::new();
        node.insert("@id".to_string(), Value::String(subj.to_string()));

        // Group by predicate
        let mut pred_map: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for (pred, obj) in pred_objects {
            pred_map.entry(pred).or_default().push(obj);
        }

        for (pred, objects) in &pred_map {
            let obj_values: Vec<Value> = objects
                .iter()
                .map(|o| {
                    let mut m = serde_json::Map::new();
                    m.insert("@id".to_string(), Value::String(o.to_string()));
                    Value::Object(m)
                })
                .collect();
            if obj_values.len() == 1 {
                node.insert(pred.to_string(), obj_values.into_iter().next().unwrap());
            } else {
                node.insert(pred.to_string(), Value::Array(obj_values));
            }
        }

        graph_nodes.push(Value::Object(node));
    }

    // Nodes that are only objects (never subjects) also get an entry
    let subject_set: HashSet<&str> = subject_map.keys().copied().collect();
    for &id in &graph.node_ids() {
        if !subject_set.contains(id) && graph.degree(id).unwrap_or(0) > 0 {
            let mut node = serde_json::Map::new();
            node.insert("@id".to_string(), Value::String(id.to_string()));
            graph_nodes.push(Value::Object(node));
        }
    }

    let mut doc = serde_json::Map::new();
    doc.insert("@graph".to_string(), Value::Array(graph_nodes));

    serde_json::to_string_pretty(&Value::Object(doc))
        .map_err(|e| format!("JSON serialization error: {}", e))
}

#[cfg(test)]
mod tests {
    use super::*;

    const TURTLE_DATA: &str = r#"
@prefix ex: <http://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Animal a rdfs:Class .
ex:Dog a rdfs:Class ;
    rdfs:subClassOf ex:Animal ;
    rdfs:label "Dog" .
ex:Cat a rdfs:Class ;
    rdfs:subClassOf ex:Animal ;
    rdfs:label "Cat" .
ex:Poodle a rdfs:Class ;
    rdfs:subClassOf ex:Dog .
"#;

    #[test]
    fn test_load_turtle() {
        let (graph, stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        assert!(stats.total_triples > 0, "triples: {}", stats.total_triples);
        assert!(graph.n_nodes() > 0);
        assert!(graph.n_edges() > 0);

        let dog = "http://example.org/Dog";
        let animal = "http://example.org/Animal";
        assert!(graph.has_node(dog));
        assert!(graph.has_node(animal));
        assert!(graph.has_edge(dog, animal));
    }

    #[test]
    fn test_load_folio() {
        let folio_path = "/tmp/FOLIO/FOLIO.owl";
        if !Path::new(folio_path).exists() {
            eprintln!("FOLIO.owl not found, skipping");
            return;
        }

        // 1. LOAD
        let (graph, stats) = load_rdf_file(folio_path).unwrap();

        eprintln!("=== FOLIO Load ===");
        eprintln!(
            "  Triples: {}  Nodes: {}  Edges: {}  Literals: {}  Time: {}ms",
            stats.total_triples,
            stats.nodes,
            stats.edges,
            stats.literal_properties,
            stats.load_time_ms
        );

        assert!(
            stats.nodes > 1000,
            "Expected >1000 nodes, got {}",
            stats.nodes
        );
        assert!(
            stats.edges > 1000,
            "Expected >1000 edges, got {}",
            stats.edges
        );

        // 2. CALCULATE — real algorithms on real data
        let start = std::time::Instant::now();
        let sccs = crate::core::algorithms::components::strongly_connected_components(&graph);
        let scc_ms = start.elapsed().as_millis();

        let start = std::time::Instant::now();
        let wcc_count = crate::core::algorithms::components::num_connected_components(&graph);
        let wcc_ms = start.elapsed().as_millis();

        let start = std::time::Instant::now();
        let ranks = crate::core::algorithms::centrality::pagerank(&graph, 0.85, 20);
        let pr_ms = start.elapsed().as_millis();

        eprintln!("=== FOLIO Algorithms ===");
        eprintln!("  SCCs: {} ({}ms)", sccs.len(), scc_ms);
        eprintln!("  Weakly connected: {} ({}ms)", wcc_count, wcc_ms);
        eprintln!(
            "  PageRank top 5: {:?} ({}ms)",
            &ranks[..5.min(ranks.len())],
            pr_ms
        );

        // 3. SAVE — JSON serialize
        let start = std::time::Instant::now();
        let json = graph.to_json().unwrap();
        let ser_ms = start.elapsed().as_millis();
        eprintln!("=== FOLIO Save ===");
        eprintln!("  JSON: {} bytes ({}ms)", json.len(), ser_ms);

        // 4. LOAD — JSON deserialize (round-trip)
        let start = std::time::Instant::now();
        let graph2 = Graph::from_json(&json).unwrap();
        let deser_ms = start.elapsed().as_millis();
        eprintln!("  Deserialize: ({}ms)", deser_ms);

        // 5. VERIFY — exact match
        assert_eq!(
            graph.n_nodes(),
            graph2.n_nodes(),
            "Node count mismatch after round-trip"
        );
        assert_eq!(
            graph.n_edges(),
            graph2.n_edges(),
            "Edge count mismatch after round-trip"
        );

        // Run PageRank again on deserialized graph to verify algorithms work identically
        let ranks2 = crate::core::algorithms::centrality::pagerank(&graph2, 0.85, 20);
        assert_eq!(
            ranks[0].0, ranks2[0].0,
            "Top PageRank node mismatch after round-trip"
        );
        assert!(
            (ranks[0].1 - ranks2[0].1).abs() < 1e-10,
            "Top PageRank score mismatch after round-trip"
        );

        eprintln!("=== Round-trip verified ===");
    }

    #[test]
    fn test_export_turtle() {
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let turtle = export_turtle(&graph).unwrap();

        // Turtle output should contain the expected IRIs
        assert!(
            turtle.contains("http://example.org/Dog") || turtle.contains("example.org/Dog"),
            "Turtle should contain Dog IRI, got:\n{}",
            turtle
        );
        assert!(
            turtle.contains("http://example.org/Animal") || turtle.contains("example.org/Animal"),
            "Turtle should contain Animal IRI"
        );
        assert!(
            turtle.contains("http://www.w3.org/2000/01/rdf-schema#subClassOf")
                || turtle.contains("subClassOf"),
            "Turtle should contain subClassOf predicate"
        );
    }

    #[test]
    fn test_export_ntriples() {
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let nt = export_ntriples(&graph).unwrap();

        // N-Triples uses full IRIs in angle brackets
        assert!(
            nt.contains("<http://example.org/Dog>"),
            "N-Triples should contain <Dog IRI>, got:\n{}",
            nt
        );
        assert!(
            nt.contains("<http://example.org/Animal>"),
            "N-Triples should contain <Animal IRI>"
        );
        // Each line should end with " ."
        for line in nt.lines() {
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                assert!(
                    trimmed.ends_with(" ."),
                    "N-Triple line should end with ' .': {}",
                    trimmed
                );
            }
        }
    }

    #[test]
    fn test_turtle_roundtrip() {
        // Load original turtle, export, re-import, verify counts match
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let turtle = export_turtle(&graph).unwrap();

        let (graph2, _stats2) = load_rdf_string(&turtle, RdfFormat::Turtle).unwrap();

        // Edge counts should match exactly (only IRI-to-IRI edges are exported)
        assert_eq!(
            graph.n_edges(),
            graph2.n_edges(),
            "Edge count mismatch: original={}, roundtrip={}",
            graph.n_edges(),
            graph2.n_edges()
        );
        // Node count in roundtrip should match: exported triples only reference
        // nodes that were edge endpoints, so roundtrip should have the same nodes.
        assert_eq!(
            graph.n_nodes(),
            graph2.n_nodes(),
            "Node count mismatch: original={}, roundtrip={}",
            graph.n_nodes(),
            graph2.n_nodes()
        );
    }

    #[test]
    fn test_ntriples_roundtrip() {
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let nt = export_ntriples(&graph).unwrap();

        let (graph2, _stats2) = load_rdf_string(&nt, RdfFormat::NTriples).unwrap();

        assert_eq!(graph.n_edges(), graph2.n_edges());
        assert_eq!(graph.n_nodes(), graph2.n_nodes());
    }

    #[test]
    fn test_export_default_predicate() {
        // Graph with edges that have no "predicate" property should use the default
        let mut graph = Graph::new(true);
        let props = HashMap::new();
        graph
            .add_node("http://example.org/A", props.clone())
            .unwrap();
        graph.add_node("http://example.org/B", props).unwrap();
        graph
            .add_edge(
                "http://example.org/A",
                "http://example.org/B",
                HashMap::new(),
            )
            .unwrap();

        let nt = export_ntriples(&graph).unwrap();
        assert!(
            nt.contains("<http://kaos.273v.com/graph#relatedTo>"),
            "Should use default predicate, got:\n{}",
            nt
        );
    }

    #[test]
    fn test_export_blank_nodes() {
        // Test that blank nodes (starting with "_:") are handled
        let mut graph = Graph::new(true);
        let props = HashMap::new();
        graph
            .add_node("http://example.org/A", props.clone())
            .unwrap();
        graph.add_node("_:b0", props).unwrap();
        let mut edge_props = HashMap::new();
        edge_props.insert(
            "predicate".to_string(),
            Value::String("http://example.org/knows".to_string()),
        );
        graph
            .add_edge("http://example.org/A", "_:b0", edge_props)
            .unwrap();

        let nt = export_ntriples(&graph).unwrap();
        assert!(
            nt.contains("_:b0"),
            "Should contain blank node _:b0, got:\n{}",
            nt
        );
        assert!(
            nt.contains("<http://example.org/A>"),
            "Should contain named node A"
        );
    }

    #[test]
    fn test_rdf_edges_have_type_property() {
        // Edges loaded from RDF should have both "predicate" (full IRI) and "type" (short name)
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let dog = "http://example.org/Dog";
        let animal = "http://example.org/Animal";

        // Find the Dog -> Animal edge
        let edges = graph.edges_vec();
        let dog_animal = edges
            .iter()
            .find(|(s, t, _)| *s == dog && *t == animal)
            .expect("Dog -> Animal edge should exist");

        // Should have "predicate" = full IRI
        let pred = dog_animal
            .2
            .properties
            .get("predicate")
            .and_then(|v| v.as_str());
        assert_eq!(
            pred,
            Some("http://www.w3.org/2000/01/rdf-schema#subClassOf"),
            "Edge should have full predicate IRI"
        );

        // Should have "type" = short name
        let edge_type = dog_animal.2.properties.get("type").and_then(|v| v.as_str());
        assert_eq!(
            edge_type,
            Some("subClassOf"),
            "Edge should have short 'type' for schema validation"
        );
    }

    #[test]
    fn test_export_uses_type_if_predicate_absent() {
        // Graph with "type" but no "predicate" should use "type" for export
        let mut graph = Graph::new(true);
        let props = HashMap::new();
        graph
            .add_node("http://example.org/A", props.clone())
            .unwrap();
        graph.add_node("http://example.org/B", props).unwrap();
        let mut edge_props = HashMap::new();
        edge_props.insert(
            "type".to_string(),
            Value::String("http://example.org/knows".to_string()),
        );
        graph
            .add_edge("http://example.org/A", "http://example.org/B", edge_props)
            .unwrap();

        let nt = export_ntriples(&graph).unwrap();
        assert!(
            nt.contains("<http://example.org/knows>"),
            "Should use 'type' property as predicate IRI, got:\n{}",
            nt
        );
    }

    #[test]
    fn test_export_jsonld_basic() {
        let (graph, _stats) = load_rdf_string(TURTLE_DATA, RdfFormat::Turtle).unwrap();
        let jsonld = export_jsonld(&graph).unwrap();

        // Parse to verify it's valid JSON
        let parsed: Value = serde_json::from_str(&jsonld).unwrap();
        assert!(parsed.get("@graph").is_some(), "Should have @graph key");

        let graph_arr = parsed["@graph"].as_array().unwrap();
        assert!(!graph_arr.is_empty(), "Graph should not be empty");

        // Should contain @id fields
        assert!(jsonld.contains("@id"), "JSON-LD should contain @id fields");
        assert!(
            jsonld.contains("http://example.org/Dog"),
            "Should contain Dog IRI"
        );
    }

    #[test]
    fn test_export_jsonld_empty_graph() {
        let graph = Graph::new(true);
        let jsonld = export_jsonld(&graph).unwrap();
        let parsed: Value = serde_json::from_str(&jsonld).unwrap();
        let graph_arr = parsed["@graph"].as_array().unwrap();
        assert!(graph_arr.is_empty());
    }

    #[test]
    fn test_export_jsonld_default_predicate() {
        let mut graph = Graph::new(true);
        let props = HashMap::new();
        graph
            .add_node("http://example.org/A", props.clone())
            .unwrap();
        graph.add_node("http://example.org/B", props).unwrap();
        graph
            .add_edge(
                "http://example.org/A",
                "http://example.org/B",
                HashMap::new(),
            )
            .unwrap();

        let jsonld = export_jsonld(&graph).unwrap();
        assert!(
            jsonld.contains(DEFAULT_PREDICATE),
            "Should use default predicate, got:\n{}",
            jsonld
        );
    }
}
