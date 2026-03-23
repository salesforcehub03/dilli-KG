from services.neo4j_service import driver

def find_belinostat():
    if not driver:
        print("Driver not initialized.")
        return
        
    query = "MATCH (d:Drug) WHERE toLower(d.drug_name) CONTAINS 'belinostat' RETURN d.drug_name"
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            print(record["d.drug_name"])

if __name__ == "__main__":
    find_belinostat()
