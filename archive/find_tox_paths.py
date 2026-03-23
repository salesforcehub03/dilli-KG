from services.neo4j_service import driver

def find_tox_nodes(drug_name):
    queries = {
        "PreclinicalStudy_Path": f"MATCH (d:Drug)-[*1..3]-(ps:PreclinicalStudy) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ps) as count",
        "AdverseEvent_Path": f"MATCH (d:Drug)-[*1..3]-(ae:AdverseEvent) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(ae) as count",
        "Exposure_Path": f"MATCH (d:Drug)-[*1..4]-(em:ExposureMeasurement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN count(em) as count"
    }
    results = {}
    with driver.session() as s:
        for name, q in queries.items():
            res = s.run(q)
            results[name] = res.single()['count']
            
            # If found, let's see the path
            if results[name] > 0:
                path_query = f"MATCH p=(d:Drug)-[*1..4]-(n) WHERE toLower(d.drug_name) = toLower('{drug_name}') AND labels(n) CONTAINS '{name.split('_')[0]}' RETURN [rel in relationships(p) | type(rel)] as rels, labels(n) as target_labels LIMIT 1"
                path_res = s.run(path_query)
                p_info = path_res.single()
                if p_info:
                    results[name + "_path"] = p_info['rels']
    return results

if __name__ == "__main__":
    import json
    all_res = {}
    for drug in ["Vorinostat", "Resminostat", "Belinostat", "Panobinostat"]:
        all_res[drug] = find_tox_nodes(drug)
    with open("tox_path_results.json", "w") as f:
        json.dump(all_res, f, indent=4)
