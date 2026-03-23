from services.neo4j_service import driver

query_orphans = """
MATCH (n)
WHERE (toLower(n.drug) = 'vorinostat' OR toLower(n.drug_name) = 'vorinostat' OR toLower(n.name) CONTAINS 'vorinostat')
  AND NOT ('Drug' IN labels(n))
  AND NOT (n)-[]-(:Drug)
RETURN labels(n) as labels, count(n) as count
"""

query_all_types = """
MATCH (n)
WHERE (toLower(n.drug) = 'vorinostat' OR toLower(n.drug_name) = 'vorinostat' OR toLower(n.name) CONTAINS 'vorinostat')
  AND NOT ('Drug' IN labels(n))
RETURN labels(n) as labels, count(n) as count
"""

with driver.session() as session:
    print("--- ORPHAN NODES (No links to ANY drug) ---")
    res = session.run(query_orphans)
    for r in res:
        print(f"{r['labels'][0]}: {r['count']}")
        
    print("\n--- ALL NODES referencing Vorinostat ---")
    res2 = session.run(query_all_types)
    for r in res2:
        print(f"{r['labels'][0]}: {r['count']}")
