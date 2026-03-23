from services.neo4j_service import driver

def check_2nd_degree(drug_name):
    query = f"""
    MATCH (d:Drug {{drug_name: '{drug_name}'}})-[:HAS_PRECLINICAL_DATA]->(pd)-[*1..2]-(n)
    RETURN labels(n) as labels, keys(n) as keys, n.name as name
    """
    with driver.session() as s:
        res = s.run(query)
        for r in res:
            print(f"LABELS: {r['labels']} | KEYS: {r['keys']} | NAME: {r['name']}")

if __name__ == "__main__":
    check_2nd_degree("Vorinostat")
