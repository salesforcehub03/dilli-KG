from services.neo4j_service import driver

def explore_belinostat():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[r]->(n)
    RETURN type(r) as rel, count(n) as count, labels(n) as labels
    """
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(f"Relationship: {record['rel']}, Count: {record['count']}, Labels: {record['labels']}")

if __name__ == "__main__":
    explore_belinostat()
