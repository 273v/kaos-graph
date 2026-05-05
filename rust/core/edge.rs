use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Data stored on each graph edge.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EdgeData {
    pub properties: HashMap<String, Value>,
}

// PartialEq + PartialOrd are required by petgraph's articulation_points algorithm.
// Since EdgeData's properties are arbitrary JSON, we use identity equality and
// a trivial ordering that considers all EdgeData as equal for ordering purposes.
impl PartialEq for EdgeData {
    fn eq(&self, other: &Self) -> bool {
        self.properties == other.properties
    }
}

impl PartialOrd for EdgeData {
    fn partial_cmp(&self, _other: &Self) -> Option<std::cmp::Ordering> {
        // All edges are considered equal for ordering. This satisfies the
        // petgraph trait bound without imposing an arbitrary order on JSON values.
        Some(std::cmp::Ordering::Equal)
    }
}
