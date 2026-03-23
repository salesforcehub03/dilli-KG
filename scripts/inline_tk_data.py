from services.neo4j_service import driver

def update_tk_nodes_properties():
    query_rat = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Rat'})
    SET tk.measurements_data = '
    Dose 10mg/kg/day:
    - Male: Cmax(day 1,5,151)=1.14, 1.25, 2.63 | AUC(day 1,5,151)=0.27, 0.28, 0.71
    - Female: Cmax(day 1,5,151)=1.85, 1.64, 2.48 | AUC(day 1,5,151)=0.4, 0.39, 0.53
    Dose 25mg/kg/day:
    - Male: Cmax(day 1,5,151)=3.13, 4.66, 7.64 | AUC(day 1,5,151)=0.81, 0.97, 2.22
    - Female: Cmax(day 1,5,151)=4.56, 4.36, 6.15 | AUC(day 1,5,151)=1.01, 1.13, 1.76
    Dose 100mg/kg/day:
    - Male: Cmax(day 1,5,151)=14.06, 17.71, 30.34 | AUC(day 1,5,151)=5.87, 11.07, 18.45
    - Female: Cmax(day 1,5,151)=23.87, 23.65, 37.10 | AUC(day 1,5,151)=6.81, 7.17, 12.09
    '
    RETURN tk
    """
    
    query_dog = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Dog'})
    SET tk.measurements_data = '
    Dose 10mg/kg/day:
    - Male: Cmax(day 1,5,151)=2.9, 2.9, 4.2 | AUC(day 1,5,151)=1.3, 1.7, 2.7
    - Female: Cmax(day 1,5,151)=3.9, 4.5, 3.8 | AUC(day 1,5,151)=1.6, 2.3, 2.2
    Dose 25mg/kg/day:
    - Male: Cmax(day 1,5,151)=10.5, 8.3, 10.3 | AUC(day 1,5,151)=4.3, 4.2, 6.1
    - Female: Cmax(day 1,5,151)=8.5, 8.4, 11.2 | AUC(day 1,5,151)=4.4, 4.3, 5.8
    Dose 50mg/kg/day:
    - Male: Cmax(day 1,5,151)=17.7, 18.5, 21.0 | AUC(day 1,5,151)=9.0, 9.8, 12.5
    - Female: Cmax(day 1,5,151)=20.0, 20.3, 23.4 | AUC(day 1,5,151)=8.7, 9.8, 13.8
    '
    RETURN tk
    """

    with driver.session() as session:
        session.run(query_rat)
        session.run(query_dog)
        print("Successfully updated Rat and Dog TK parameter nodes with inline properties.")

if __name__ == "__main__":
    update_tk_nodes_properties()
