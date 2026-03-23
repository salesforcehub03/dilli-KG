from services.neo4j_service import driver
import json

def check_schema_capabilities():
    if not driver:
        print("Driver not initialized.")
        return

    queries = {
        "AdverseEvents": "MATCH (n:AdverseEvent) RETURN keys(n) LIMIT 5",
        "ClinicalData": "MATCH (n:ClinicalData) RETURN keys(n) LIMIT 5",
        "PreclinicalData": "MATCH (n:PreClinicalData) RETURN keys(n) LIMIT 5",
        "Studies": "MATCH (n:StudyOverview) RETURN keys(n) LIMIT 5",
        "SafetyData": "MATCH (n:SafetyData) RETURN keys(n) LIMIT 5",
        "Toxicokinetics": "MATCH (n:ToxicokineticParameters) RETURN keys(n) LIMIT 5"
    }
    
    with open('schema_direct.txt', 'w', encoding='utf-8') as f:
        with driver.session() as session:
            for name, query in queries.items():
                result = session.run(query)
                all_keys = set()
                for record in result:
                    for key_list in record.values():
                        all_keys.update(key_list)
                f.write(f"--- {name} ---\n")
                f.write(", ".join(all_keys) + "\n\n")
    print("Schema keys written to schema_direct.txt")

if __name__ == "__main__":
    check_schema_capabilities()
