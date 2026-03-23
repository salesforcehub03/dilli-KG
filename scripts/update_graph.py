from services.neo4j_service import driver

def update_preclinical_adverse_events():
    if not driver:
        print("[ERROR] Database driver not configured.")
        return

    # Update Male PreclinicalStudy nodes for Vorinostat and Panobinostat
    query_male = """
    MATCH (d:Drug)
    WHERE d.drug_name IN ['Vorinostat', 'Panobinostat']
    MATCH (d)-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_PRECLINICAL_STUDY]->(study:PreclinicalStudy)
    WHERE study.sex = 'M' AND d.adverse_events_male IS NOT NULL
    SET study.adverse_events = d.adverse_events_male
    RETURN d.drug_name as drug, study.sex as sex, study.adverse_events as added_events
    """

    # Update Female PreclinicalStudy nodes for Vorinostat and Panobinostat
    query_female = """
    MATCH (d:Drug)
    WHERE d.drug_name IN ['Vorinostat', 'Panobinostat']
    MATCH (d)-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_PRECLINICAL_STUDY]->(study:PreclinicalStudy)
    WHERE study.sex = 'F' AND d.adverse_events_female IS NOT NULL
    SET study.adverse_events = d.adverse_events_female
    RETURN d.drug_name as drug, study.sex as sex, study.adverse_events as added_events
    """

    with driver.session() as session:
        print("--- Updating Male Preclinical Study Nodes ---")
        result_male = session.run(query_male)
        for record in result_male:
            print(f"[{record['drug']}] ({record['sex']}) Added {len(record['added_events'])} events.")

        print("\n--- Updating Female Preclinical Study Nodes ---")
        result_female = session.run(query_female)
        for record in result_female:
            print(f"[{record['drug']}] ({record['sex']}) Added {len(record['added_events'])} events.")

    print("\n[SUCCESS] Preclinical Study adverse events updated.")

if __name__ == "__main__":
    update_preclinical_adverse_events()
