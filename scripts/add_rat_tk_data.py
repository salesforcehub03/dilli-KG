from services.neo4j_service import driver
import json

def add_rat_tk_data():
    if not driver:
        print("Driver not initialized.")
        return

    # Data to be inserted based on user input
    tk_data = [
        {"dose_group": 2, "dose_mg_kg_day": 10, "sex": "M", "cmax_day1": 1.14, "cmax_day5": 1.25, "cmax_day151": 2.63, "auc_day1": 0.27, "auc_day5": 0.28, "auc_day151": 0.71},
        {"dose_group": 2, "dose_mg_kg_day": 10, "sex": "F", "cmax_day1": 1.85, "cmax_day5": 1.64, "cmax_day151": 2.48, "auc_day1": 0.4, "auc_day5": 0.39, "auc_day151": 0.53},
        {"dose_group": 3, "dose_mg_kg_day": 25, "sex": "M", "cmax_day1": 3.13, "cmax_day5": 4.66, "cmax_day151": 7.64, "auc_day1": 0.81, "auc_day5": 0.97, "auc_day151": 2.22},
        {"dose_group": 3, "dose_mg_kg_day": 25, "sex": "F", "cmax_day1": 4.56, "cmax_day5": 4.36, "cmax_day151": 6.15, "auc_day1": 1.01, "auc_day5": 1.13, "auc_day151": 1.76},
        {"dose_group": 4, "dose_mg_kg_day": 100, "sex": "M", "cmax_day1": 14.06, "cmax_day5": 17.71, "cmax_day151": 30.34, "auc_day1": 5.87, "auc_day5": 11.07, "auc_day151": 18.45},
        {"dose_group": 4, "dose_mg_kg_day": 100, "sex": "F", "cmax_day1": 23.87, "cmax_day5": 23.65, "cmax_day151": 37.10, "auc_day1": 6.81, "auc_day5": 7.17, "auc_day151": 12.09}
    ]

    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)
    // Ensure Rat species node exists and link it if needed, or create the TK node directly under PreclinicalData
    MERGE (p)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Rat'})
    WITH tk
    UNWIND $data as row
    CREATE (tk)-[:HAS_MEASUREMENT]->(m:ToxicokineticMeasurement {
        dose_group: row.dose_group,
        dose_mg_kg_day: row.dose_mg_kg_day,
        sex: row.sex,
        cmax_ug_ml_day1: row.cmax_day1,
        cmax_ug_ml_day5: row.cmax_day5,
        cmax_ug_ml_day151: row.cmax_day151,
        auc_pg_h_ml_day1: row.auc_day1,
        auc_pg_h_ml_day5: row.auc_day5,
        auc_pg_h_ml_day151: row.auc_day151
    })
    RETURN count(m) as nodes_created
    """

    with driver.session() as session:
        result = session.run(query, data=tk_data)
        record = result.single()
        print(f"Created {record['nodes_created']} ToxicokineticMeasurement nodes for Rat.")

if __name__ == "__main__":
    add_rat_tk_data()
