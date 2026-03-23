from services.neo4j_service import driver
import json

def run_user_queries():
    if not driver:
        print("Driver not initialized.")
        return
        
    clinical_query = """
    MATCH (d:Drug {drug_name:'Belinostat'})-[:HAS_CLINICAL_DATA]->(c:ClinicalData)
    OPTIONAL MATCH (c)-[:HAS_PHARMACOKINETICS]->(pk:Pharmacokinetics)
    OPTIONAL MATCH (c)-[:HAS_ELIGIBILITY_CRITERIA]->(ec:EligibilityCriteria)
    OPTIONAL MATCH (c)-[:HAS_TREATMENT_MANAGEMENT]->(tm:TreatmentManagement)
    RETURN properties(c) as c_props, properties(pk) as pk_props, properties(ec) as ec_props, properties(tm) as tm_props
    """
    
    preclinical_query = """
    MATCH (d:Drug {drug_name:'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)
    OPTIONAL MATCH (p)-[r]->(n)
    RETURN properties(p) as p_props, type(r) as rel, labels(n) as labels, properties(n) as n_props
    """
    
    with driver.session() as session:
        print("=== CLINICAL DATA ===")
        res = session.run(clinical_query)
        for record in res:
            print(json.dumps({
                "Clinical": record["c_props"],
                "PK": record["pk_props"],
                "Eligibility": record["ec_props"],
                "Treatment": record["tm_props"]
            }, indent=2))
            
        print("\n=== PRECLINICAL DATA ===")
        res2 = session.run(preclinical_query)
        for record in res2:
            print(json.dumps({
                "PreClinical": record["p_props"],
                "Relation": record["rel"],
                "TargetLabels": record["labels"],
                "TargetProps": record["n_props"]
            }, indent=2))

if __name__ == "__main__":
    run_user_queries()
