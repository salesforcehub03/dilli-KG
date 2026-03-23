from services.neo4j_service import driver
import json

def export_rat_nodes():
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[r]-(n)
    WHERE toLower(labels(n)[0]) CONTAINS 'rat' OR toLower(n.species) = 'rat' OR toLower(n.name) CONTAINS 'rat'
    RETURN labels(n)[0] as lbl, type(r) as rel, properties(n) as props
    """
    
    query2 = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[r]->(n)
    RETURN labels(n)[0] as lbl, type(r) as rel, properties(n) as props
    """
    
    with driver.session() as session:
        result1 = session.run(query)
        r1 = [{"lbl": rec["lbl"], "rel": rec["rel"], "props": rec["props"]} for rec in result1]
        
        result2 = session.run(query2)
        r2 = [{"lbl": rec["lbl"], "rel": rec["rel"], "props": rec["props"]} for rec in result2]
        
        with open('check_rats_output.json', 'w', encoding='utf-8') as f:
            json.dump({"rat_matches": r1, "all_preclinical_children": r2}, f, indent=2)

if __name__ == "__main__":
    export_rat_nodes()
