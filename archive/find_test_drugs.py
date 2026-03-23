from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

if not all([uri, user, password]):
    print("Error: Missing Neo4j credentials in .env")
    exit(1)

driver = GraphDatabase.driver(uri, auth=(user, password))

def find_test_drugs():
    # Simple query to find drugs that actually have ANY clinical, preclinical, or AE data
    query = """
    MATCH (d:Drug)
    OPTIONAL MATCH (d)-[:HAS_CLINICAL_DATA]->(c)
    OPTIONAL MATCH (d)-[:HAS_PRECLINICAL_STUDY]->(ps)
    OPTIONAL MATCH (d)-[:HAS_ADVERSE_EVENTS]->(ae)
    WITH d, count(DISTINCT c) as clinical_count, 
           count(DISTINCT ps) as preclinical_count, 
           count(DISTINCT ae) as ae_count
    WHERE clinical_count > 0 OR preclinical_count > 0 OR ae_count > 0
    RETURN d.drug_name as name, clinical_count, preclinical_count, ae_count
    ORDER BY clinical_count + preclinical_count + ae_count DESC
    LIMIT 20
    """
    try:
        with driver.session() as session:
            results = session.run(query)
            print("-" * 60)
            print(f"{'Drug Name':<25} | {'Clin':<4} | {'Pre':<4} | {'AE':<4}")
            print("-" * 60)
            for record in results:
                print(f"{str(record['name']):<25} | {record['clinical_count']:<4} | {record['preclinical_count']:<4} | {record['ae_count']:<4}")
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    find_test_drugs()
    driver.close()
