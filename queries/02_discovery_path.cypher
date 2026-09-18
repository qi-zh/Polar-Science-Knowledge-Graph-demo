// Explore from a krill specimen to a penguin survey through shared organisms.
// The PREYS_ON arrow remains penguin -> krill even when explored from krill.
MATCH path =
  (specimen:BiologicalSpecimen)-[:SPECIMEN_OF_ORGANISM]->
  (krill:Organism)<-[:PREYS_ON]-
  (penguin:Organism)<-[:OBSERVES_ORGANISM]-
  (survey:PopulationObservation)
WHERE krill.id = 'demo_organism_6819'
  AND penguin.id = 'demo_organism_9238'
  AND specimen.id STARTS WITH 'demo_record_'
  AND survey.id STARTS WITH 'demo_record_'
RETURN specimen.name AS specimen,
       specimen.source_url AS specimen_source_url,
       krill.name AS krill,
       penguin.name AS penguin,
       survey.name AS survey,
       survey.source_url AS survey_source_url,
       path;
