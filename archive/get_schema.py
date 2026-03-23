from services.neo4j_service import driver

def get_schema():
    if not driver:
        print("No Neo4j driver available.")
        return
        
    with driver.session() as session:
        with open("schema_output.txt", "w") as f:
            f.write("=== LABELS ===\n")
            res = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [record["label"] for record in res]
            f.write(", ".join(labels) + "\n\n")
            
            f.write("=== RELATIONSHIP TYPES ===\n")
            res2 = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
            rels = [record["relationshipType"] for record in res2]
            f.write(", ".join(rels) + "\n\n")

            f.write("=== DRUG PROPERTIES ===\n")
            res3 = session.run("MATCH (d:Drug) RETURN keys(d) LIMIT 1")
            for record in res3:
                f.write(str(record.get("keys(d)", record)) + "\n")

if __name__ == "__main__":
    get_schema()
