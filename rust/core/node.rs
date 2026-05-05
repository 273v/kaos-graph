use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Data stored on each graph node.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NodeData {
    pub id: String,
    pub properties: HashMap<String, Value>,
}
