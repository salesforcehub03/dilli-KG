from services.neo4j_service import driver

def check_paths(drug_name):
    query = f"""
    MATCH p=(d:Drug {{drug_name: '{drug_name}'}})-[*1..3]-(n)
    WHERE any(l in labels(n) WHERE l IN ['PreclinicalStudy', 'AdverseEvent'])
    RETURN labels(n) as label, [rel in relationships(p) | type(rel)] as rels
    LIMIT 5
    """
    with driver.session() as s:
        res = s.run(query)
        for r in res:
            print(f"LABELS: {r['label']} | PATH: {' -> '.join(r['rels'])}")

if __name__ == "__main__":
    check_paths("Vorinostat")
