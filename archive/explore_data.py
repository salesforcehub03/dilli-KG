from services.neo4j_service import driver

def explore_drug(drug_name):
    queries = {
        "AE_Path_1": f"MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ae) AS count",
        "AE_Path_2": f"MATCH (d:Drug)-[]-(ae:AdverseEvent) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ae) AS count",
        "Clinical_Count": f"MATCH (d:Drug)-[:HAS_CLINICAL_DATA]->(c) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(c) AS count",
        "Preclinical_Count": f"MATCH (d:Drug)-[]-(ps:PreclinicalStudy) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ps) AS count",
        "Preclinical_Path_2": f"MATCH (d:Drug)-[:HAS_PRECLINICAL_STUDY]->(ps) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ps) AS count",
        "Preclinical_Data": f"MATCH (d:Drug)-[:HAS_PRECLINICAL_DATA]->(pd) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(pd) AS count"
    }
    
    results = {}
    with driver.session() as s:
        for name, q in queries.items():
            res = s.run(q)
            results[name] = res.single()['count']
    return results

if __name__ == "__main__":
    with open("explore_results_v2.txt", "w") as f:
        for drug in ["Vorinostat", "Resminostat", "Belinostat", "Panobinostat"]:
            f.write(f"\nExploration for {drug}:\n")
            res = explore_drug(drug)
            f.write(str(res) + "\n")
    print("Results written to explore_results_v2.txt")
