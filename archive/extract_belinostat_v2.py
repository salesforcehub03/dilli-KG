from services.neo4j_service import driver
import json

def get_belinostat_details():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})
    OPTIONAL MATCH (d)-[r]->(n)
    RETURN type(r) as relationship, labels(n) as labels, properties(n) as properties
    """
    
    with driver.session() as session:
        result = session.run(query)
        data_by_rel = {}
        for record in result:
            rel = record["relationship"]
            if not rel:
                continue
            if rel not in data_by_rel:
                data_by_rel[rel] = []
            data_by_rel[rel].append({
                "labels": list(record["labels"]),
                "properties": record["properties"]
            })
            
    for rel, nodes in data_by_rel.items():
        print(f"\n=== Relationship: {rel} ===")
        for node in nodes:
            print(f"Labels: {node['labels']}")
            print(f"Properties: {json.dumps(node['properties'], indent=2)}")
            print("-" * 20)

if __name__ == "__main__":
    get_belinostat_details()
