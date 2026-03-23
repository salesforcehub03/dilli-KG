from services.neo4j_service import driver

def verify():
    query = """
    MATCH (d:Drug)-[:HAS_PRECLINICAL_DATA]->(:PreClinicalData)-[:HAS_PRECLINICAL_STUDY]->(p:PreclinicalStudy)
    WHERE d.drug_name IN ['Vorinostat', 'Panobinostat']
    RETURN d.drug_name as drug, p.sex as sex, p.adverse_events as events
    """
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(f"[{record['drug']}] ({record['sex']}) Events: {record['events']}")

if __name__ == "__main__":
    verify()
