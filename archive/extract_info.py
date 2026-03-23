from services.neo4j_service import driver

def analyze_drug(drug_name):
    query = """
    MATCH (d:Drug {drug_name: $drug_name})
    OPTIONAL MATCH (d)-[:HAS_ADVERSE_EVENTS]->(:AdverseEvents)-[:HAS_EVENT]->(ae:AdverseEvent)
    OPTIONAL MATCH (d)-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)
    OPTIONAL MATCH (p)-[:HAS_ANIMAL_STUDY]->(ans:AnimalStudy)
    RETURN d.drug_name as drug, 
           collect(DISTINCT ae.name) as adverse_events,
           p.animal_type as p_animal, p.gender as p_gender,
           ans.animal_type as ans_animal, ans.gender as ans_gender,
           labels(ans) as ans_labels
    """
    with driver.session() as session:
        result = session.run(query, drug_name=drug_name)
        for record in result:
            print(dict(record))

if __name__ == "__main__":
    analyze_drug('Vorinostat')
    analyze_drug('Panobinostat')
