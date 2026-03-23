from services.neo4j_service import driver

def remove_adverse_events_from_drug():
    if not driver:
        print("[ERROR] Database driver not configured.")
        return

    query = """
    MATCH (d:Drug)
    WHERE d.drug_name IN ['Vorinostat', 'Panobinostat']
    REMOVE d.adverse_events_male, d.adverse_events_female
    RETURN d.drug_name as drug, keys(d) as current_keys
    """

    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(f"[{record['drug']}] Properties remaining: {record['current_keys']}")
            if 'adverse_events_male' not in record['current_keys'] and 'adverse_events_female' not in record['current_keys']:
                print(f"[{record['drug']}] Successfully removed adverse events properties.")

if __name__ == "__main__":
    remove_adverse_events_from_drug()
