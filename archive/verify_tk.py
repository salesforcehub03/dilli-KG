from services.neo4j_service import driver
import json

def verify_tk_data():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters)-[:HAS_MEASUREMENT]->(m:ToxicokineticMeasurement)
    RETURN properties(m) as props
    ORDER BY m.dose_group, m.sex
    """
    
    with driver.session() as session:
        result = session.run(query)
        data = [record["props"] for record in result]
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    verify_tk_data()
