from services.neo4j_service import driver
import json

def add_dog_tk_data():
    if not driver:
        print("Driver not initialized.")
        return

    # Data to be inserted based on user input
    tk_data = [
        {"dose_mg_kg_day": 10, "sex": "M", "cmax_day1": 2.9, "cmax_day5": 2.9, "cmax_day151": 4.2, "auc_day1": 1.3, "auc_day5": 1.7, "auc_day151": 2.7},
        {"dose_mg_kg_day": 10, "sex": "F", "cmax_day1": 3.9, "cmax_day5": 4.5, "cmax_day151": 3.8, "auc_day1": 1.6, "auc_day5": 2.3, "auc_day151": 2.2},
        {"dose_mg_kg_day": 25, "sex": "M", "cmax_day1": 10.5, "cmax_day5": 8.3, "cmax_day151": 10.3, "auc_day1": 4.3, "auc_day5": 4.2, "auc_day151": 6.1},
        {"dose_mg_kg_day": 25, "sex": "F", "cmax_day1": 8.5, "cmax_day5": 8.4, "cmax_day151": 11.2, "auc_day1": 4.4, "auc_day5": 4.3, "auc_day151": 5.8},
        {"dose_mg_kg_day": 50, "sex": "M", "cmax_day1": 17.7, "cmax_day5": 18.5, "cmax_day151": 21.0, "auc_day1": 9.0, "auc_day5": 9.8, "auc_day151": 12.5},
        {"dose_mg_kg_day": 50, "sex": "F", "cmax_day1": 20.0, "cmax_day5": 20.3, "cmax_day151": 23.4, "auc_day1": 8.7, "auc_day5": 9.8, "auc_day151": 13.8}
    ]

    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)
    // Ensure Dog species node exists and link it directly under PreclinicalData
    MERGE (p)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Dog'})
    WITH tk
    UNWIND $data as row
    CREATE (tk)-[:HAS_MEASUREMENT]->(m:ToxicokineticMeasurement {
        dose_mg_kg_day: row.dose_mg_kg_day,
        sex: row.sex,
        cmax_ug_ml_day1: row.cmax_day1,
        cmax_ug_ml_day5: row.cmax_day5,
        cmax_ug_ml_day151: row.cmax_day151,
        auc_0_24h_ug_h_ml_day1: row.auc_day1,
        auc_0_24h_ug_h_ml_day5: row.auc_day5,
        auc_0_24h_ug_h_ml_day151: row.auc_day151
    })
    RETURN count(m) as nodes_created
    """

    with driver.session() as session:
        result = session.run(query, data=tk_data)
        record = result.single()
        print(f"Created {record['nodes_created']} ToxicokineticMeasurement nodes for Dog.")

if __name__ == "__main__":
    add_dog_tk_data()
