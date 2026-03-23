from services.neo4j_service import driver

def check_vorinostat():
    query = "MATCH (d:Drug {drug_name: 'Vorinostat'})-[:HAS_PRECLINICAL_DATA]->(n) RETURN labels(n) as labels, keys(n) as keys"
    with driver.session() as s:
        res = s.run(query)
        for r in res:
            print(f"Labels: {r['labels']}")
            print(f"Keys: {r['keys']}")

if __name__ == "__main__":
    check_vorinostat()
