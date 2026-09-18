// Stored source fields for the two demonstration records.
MATCH (record)
WHERE record.id STARTS WITH 'demo_record_'
RETURN record.id AS record_id,
       record.name AS record_name,
       labels(record) AS labels,
       record.platform_name AS platform_name,
       record.source_record_key AS source_record_key,
       record.record_unit AS record_unit,
       record.source_url AS source_url
ORDER BY record_id;

// The scientific relation's source is separate from the organism identities.
MATCH (penguin:Organism)-[relation:PREYS_ON]->(krill:Organism)
WHERE penguin.id = 'demo_organism_9238'
  AND krill.id = 'demo_organism_6819'
RETURN penguin.name AS source_organism,
       type(relation) AS relationship_type,
       krill.name AS target_organism,
       relation.source_name AS source_name,
       relation.source_url AS source_url;
