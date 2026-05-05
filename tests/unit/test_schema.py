"""Tests for GraphSchema validation."""

from kaos_graph import Graph
from kaos_graph.schema import EdgeType, GraphSchema, NodeType, SchemaViolation


def _make_person_org_schema() -> GraphSchema:
    """Helper: schema with Person and Organization node types, works_at edge type."""
    return GraphSchema(
        node_types=[
            NodeType(name="Person", required_properties=["name"]),
            NodeType(name="Organization", required_properties=["name", "industry"]),
        ],
        edge_types=[
            EdgeType(
                name="works_at",
                source_type="Person",
                target_type="Organization",
                required_properties=["since"],
            ),
        ],
    )


class TestSchemaValidation:
    def test_valid_graph(self):
        """Graph that fully matches schema produces zero violations."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("alice", type="Person", name="Alice")
        g.add_node("acme", type="Organization", name="Acme Corp", industry="Tech")
        g.add_edge("alice", "acme", type="works_at", since=2020)

        violations = schema.validate(g)
        assert violations == []

    def test_missing_required_property(self):
        """Node missing a required property produces a violation."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("alice", type="Person")  # missing "name"

        violations = schema.validate(g)
        assert len(violations) == 1
        v = violations[0]
        assert v.kind == "missing_property"
        assert v.element_id == "alice"
        assert "name" in v.message

    def test_unknown_node_type(self):
        """Node with a type not defined in the schema is flagged."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("server1", type="Server", hostname="srv1.example.com")

        violations = schema.validate(g)
        assert len(violations) == 1
        assert violations[0].kind == "unknown_node_type"
        assert violations[0].element_id == "server1"

    def test_unknown_edge_type(self):
        """Edge with a type not defined in the schema is flagged."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("alice", type="Person", name="Alice")
        g.add_node("bob", type="Person", name="Bob")
        g.add_edge("alice", "bob", type="knows")

        violations = schema.validate(g)
        assert len(violations) == 1
        assert violations[0].kind == "unknown_edge_type"
        assert violations[0].element_id == "alice->bob"

    def test_invalid_source_type(self):
        """Edge whose source has the wrong node type is flagged."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("acme", type="Organization", name="Acme", industry="Tech")
        g.add_node("globex", type="Organization", name="Globex", industry="Evil")
        # works_at requires source=Person, but we use Organization->Organization
        g.add_edge("acme", "globex", type="works_at", since=2020)

        violations = schema.validate(g)
        source_violations = [v for v in violations if v.kind == "invalid_source_type"]
        assert len(source_violations) == 1
        assert "Person" in source_violations[0].message
        assert "Organization" in source_violations[0].message

    def test_invalid_target_type(self):
        """Edge whose target has the wrong node type is flagged."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("alice", type="Person", name="Alice")
        g.add_node("bob", type="Person", name="Bob")
        # works_at requires target=Organization, but target is Person
        g.add_edge("alice", "bob", type="works_at", since=2020)

        violations = schema.validate(g)
        target_violations = [v for v in violations if v.kind == "invalid_target_type"]
        assert len(target_violations) == 1
        assert "Organization" in target_violations[0].message
        assert "Person" in target_violations[0].message

    def test_edge_missing_property(self):
        """Edge missing a required property produces a violation."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("alice", type="Person", name="Alice")
        g.add_node("acme", type="Organization", name="Acme", industry="Tech")
        g.add_edge("alice", "acme", type="works_at")  # missing "since"

        violations = schema.validate(g)
        prop_violations = [v for v in violations if v.kind == "missing_property"]
        assert len(prop_violations) == 1
        assert "since" in prop_violations[0].message
        assert prop_violations[0].element_id == "alice->acme"

    def test_empty_schema_accepts_all(self):
        """An empty schema (no node/edge types) accepts any graph."""
        schema = GraphSchema()
        g = Graph()
        g.add_node("a", type="Anything", foo="bar")
        g.add_node("b", type="Whatever")
        g.add_edge("a", "b", type="random_edge", x=1)

        violations = schema.validate(g)
        assert violations == []

    def test_no_type_property(self):
        """Nodes without a 'type' property are not validated against node types."""
        schema = _make_person_org_schema()
        g = Graph()
        g.add_node("untyped_node", name="Just a node")
        g.add_node("another", color="blue")

        violations = schema.validate(g)
        assert violations == []


class TestSchemaViolationFields:
    """Verify SchemaViolation dataclass fields."""

    def test_violation_is_frozen(self):
        v = SchemaViolation(kind="test", element_id="x", message="msg")
        assert v.kind == "test"
        assert v.element_id == "x"
        assert v.message == "msg"


class TestNodeTypeEdgeTypeDefaults:
    """Verify dataclass defaults for NodeType and EdgeType."""

    def test_node_type_defaults(self):
        nt = NodeType(name="Foo")
        assert nt.required_properties == []
        assert nt.optional_properties == []

    def test_edge_type_defaults(self):
        et = EdgeType(name="Bar")
        assert et.source_type is None
        assert et.target_type is None
        assert et.required_properties == []
