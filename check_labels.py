from services.neo4j_service import driver

def check():
    with driver.session() as session:
        result = session.run("CALL db.labels()")
        labels = [record["label"] for record in result]
        print(f"LABELS: {labels}")

if __name__ == "__main__":
    check()
