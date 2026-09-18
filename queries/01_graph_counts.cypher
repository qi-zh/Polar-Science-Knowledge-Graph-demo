// Read-only queries for the independently imported demonstration graph.
// The identifier prefix keeps these counts scoped to demonstration nodes.
MATCH (node)
WHERE node.id STARTS WITH 'demo_'
RETURN node.node_type AS node_type, count(node) AS node_count
ORDER BY node_type;

MATCH (source)-[relation]->(target)
WHERE source.id STARTS WITH 'demo_' AND target.id STARTS WITH 'demo_'
RETURN type(relation) AS relationship_type, count(relation) AS relation_count
ORDER BY relationship_type;
