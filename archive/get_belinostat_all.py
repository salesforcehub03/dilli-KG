from services.neo4j_service import driver
import json

def get_all_belinostat_data():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[r]-(n)
    RETURN type(r) as rel, labels(n) as labels, properties(n) as props
    """
    
    all_data = []
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            all_data.append({
                "rel": record["rel"],
                "labels": list(record["labels"]),
                "props": record["props"]
            })
            
    print(json.dumps(all_data, indent=2))

if __name__ == "__main__":
    get_all_belinostat_data()
