import json
from services.neo4j_service import driver

def check_studies():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug)-[*1..2]->(target)
    WHERE d.drug_name IN ['Vorinostat', 'Panobinostat']
    AND ('male' IN toLower(target.gender) OR 'female' IN toLower(target.gender) OR target.gender IS NOT NULL OR labels(target)[0] = 'AnimalStudy')
    RETURN d.drug_name, labels(target), properties(target) LIMIT 20
    """
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(f"Drug: {record['d.drug_name']}")
            print(f"Node Type: {record['labels(target)']}")
            print(f"Properties: {record['properties(target)']}")
            print("-" * 40)

if __name__ == "__main__":
    check_studies()
