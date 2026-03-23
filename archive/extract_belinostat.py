from services.neo4j_service import driver
import json

def get_belinostat_data():
    if not driver:
        print("Driver not initialized.")
        return
        
    queries = {
        "Drug Info": "MATCH (d:Drug {drug_name: 'Belinostat'}) RETURN properties(d) as data",
        "PreClinical Data": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData) RETURN properties(p) as data",
        "Clinical Data": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_CLINICAL_DATA]->(c:ClinicalData) RETURN properties(c) as data",
        "Adverse Events": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_ADVERSE_EVENTS]->(ae:AdverseEvents)-[:HAS_EVENT]->(e:AdverseEvent) RETURN properties(e) as data",
        "Pharmacokinetics": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PHARMACOKINETICS]->(pk:Pharmacokinetics) RETURN properties(pk) as data",
        "Mechanism of Action": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_MECHANISM_OF_ACTION]->(moa:MechanismOfAction) RETURN properties(moa) as data",
        "Toxicity": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_TOXICITY]->(t:Toxicity) RETURN properties(t) as data",
        "Preclinical Study": "MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_STUDY]->(ps:PreclinicalStudy) RETURN properties(ps) as data"
    }
    
    results = {}
    with driver.session() as session:
        for category, query in queries.items():
            res = session.run(query)
            results[category] = [record["data"] for record in res]
            
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    get_belinostat_data()
