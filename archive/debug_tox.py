from services.neo4j_service import driver

def debug_tox_queries(drug_name):
    queries = {
        "Clinical": f"MATCH (d:Drug)-[:HAS_CLINICAL_DATA]->(c) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(c) AS count",
        "Preclinical": f"MATCH (d:Drug)-[:HAS_PRECLINICAL_STUDY]->(ps) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ps) AS count",
        "AdverseEvents": f"MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ae) AS count",
        "Exposure": f"MATCH (d:Drug)-[:HAS_PRECLINICAL_TOXICOLOGY]->(pt)-[:HAS_GROUP]->(eg)-[:HAS_EXPOSURE]->(exp)-[:HAS_MEASUREMENT]->(em:ExposureMeasurement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(em) AS count",
        "GenericStudy": f"MATCH (d:Drug)-[:HAS_PRECLINICAL_STUDY]-(n) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(n) AS count",
        "GenericAE": f"MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]-(c)-[:HAS_EVENT]-(e) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(e) AS count"
    }
    
    results = {}
    with driver.session() as session:
        for name, q in queries.items():
            res = session.run(q)
            single = res.single()
            count = single["count"] if single else 0
            results[name] = count
    return results

if __name__ == "__main__":
    import json
    all_results = {}
    for drug in ["Resminostat", "Vorinostat", "Belinostat", "Panobinostat"]:
        all_results[drug] = debug_tox_queries(drug)
    
    with open("debug_results.json", "w") as f:
        json.dump(all_results, f, indent=4)
    print("Results written to debug_results.json")
