from services.neo4j_service import driver

def deep_explore_belinostat():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[r]-(n)
    RETURN type(r) as rel, startNode(r) = d as is_outgoing, labels(n) as labels, properties(n) as props LIMIT 50
    """
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            dir_str = "->" if record["is_outgoing"] else "<-"
            print(f"Drug {dir_str} [{record['rel']}] {dir_str} Node{record['labels']}")
            print(f"Props: {record['props']}")
            print("-" * 20)

if __name__ == "__main__":
    deep_explore_belinostat()
