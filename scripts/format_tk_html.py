from services.neo4j_service import driver

def update_tk_nodes_properties_html():
    rat_html = """
    <table style="width:100%; font-size:0.85rem; border-collapse:collapse; border:1px solid #ddd; border-radius:6px; overflow:hidden;">
        <thead style="background:#f8f9fa;">
            <tr>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Dose</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Sex</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Cmax (Days 1, 5, 151)</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">AUC (Days 1, 5, 151)</th>
            </tr>
        </thead>
        <tbody>
            <!-- Dose 10 -->
            <tr><td rowspan="2" style="padding:8px; border-bottom:1px solid #ddd; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">10 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee;">1.14, 1.25, 2.63</td><td style="padding:8px; border-bottom:1px dashed #eee;">0.27, 0.28, 0.71</td></tr>
            <tr><td style="padding:8px; border-bottom:1px solid #ddd;">F</td><td style="padding:8px; border-bottom:1px solid #ddd;">1.85, 1.64, 2.48</td><td style="padding:8px; border-bottom:1px solid #ddd;">0.40, 0.39, 0.53</td></tr>
            
            <!-- Dose 25 -->
            <tr><td rowspan="2" style="padding:8px; border-bottom:1px solid #ddd; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">25 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee;">3.13, 4.66, 7.64</td><td style="padding:8px; border-bottom:1px dashed #eee;">0.81, 0.97, 2.22</td></tr>
            <tr><td style="padding:8px; border-bottom:1px solid #ddd;">F</td><td style="padding:8px; border-bottom:1px solid #ddd;">4.56, 4.36, 6.15</td><td style="padding:8px; border-bottom:1px solid #ddd;">1.01, 1.13, 1.76</td></tr>
            
            <!-- Dose 100 -->
            <tr style="background:#fdfcfc;"><td rowspan="2" style="padding:8px; border-bottom:0; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">100 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee; font-weight:600; color:#c0392b;">14.06, 17.71, 30.34</td><td style="padding:8px; border-bottom:1px dashed #eee; font-weight:600; color:#c0392b;">5.87, 11.07, 18.45</td></tr>
            <tr style="background:#fdfcfc;"><td style="padding:8px; border-bottom:0;">F</td><td style="padding:8px; border-bottom:0; font-weight:600; color:#c0392b;">23.87, 23.65, 37.10</td><td style="padding:8px; border-bottom:0; font-weight:600; color:#c0392b;">6.81, 7.17, 12.09</td></tr>
        </tbody>
    </table>
    """
    
    dog_html = """
    <table style="width:100%; font-size:0.85rem; border-collapse:collapse; border:1px solid #ddd; border-radius:6px; overflow:hidden;">
        <thead style="background:#f8f9fa;">
            <tr>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Dose</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Sex</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">Cmax (Days 1, 5, 151)</th>
                <th style="padding:8px; border-bottom:2px solid #ddd; text-align:left; color:#333;">AUC (Days 1, 5, 151)</th>
            </tr>
        </thead>
        <tbody>
            <!-- Dose 10 -->
            <tr><td rowspan="2" style="padding:8px; border-bottom:1px solid #ddd; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">10 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee;">2.9, 2.9, 4.2</td><td style="padding:8px; border-bottom:1px dashed #eee;">1.3, 1.7, 2.7</td></tr>
            <tr><td style="padding:8px; border-bottom:1px solid #ddd;">F</td><td style="padding:8px; border-bottom:1px solid #ddd;">3.9, 4.5, 3.8</td><td style="padding:8px; border-bottom:1px solid #ddd;">1.6, 2.3, 2.2</td></tr>
            
            <!-- Dose 25 -->
            <tr><td rowspan="2" style="padding:8px; border-bottom:1px solid #ddd; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">25 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee;">10.5, 8.3, 10.3</td><td style="padding:8px; border-bottom:1px dashed #eee;">4.3, 4.2, 6.1</td></tr>
            <tr><td style="padding:8px; border-bottom:1px solid #ddd;">F</td><td style="padding:8px; border-bottom:1px solid #ddd;">8.5, 8.4, 11.2</td><td style="padding:8px; border-bottom:1px solid #ddd;">4.4, 4.3, 5.8</td></tr>
            
            <!-- Dose 50 -->
            <tr style="background:#fdfcfc;"><td rowspan="2" style="padding:8px; border-bottom:0; border-right:1px solid #eee; vertical-align:middle; font-weight:bold;">50 mg/kg</td><td style="padding:8px; border-bottom:1px dashed #eee;">M</td><td style="padding:8px; border-bottom:1px dashed #eee; font-weight:600; color:#c0392b;">17.7, 18.5, 21.0</td><td style="padding:8px; border-bottom:1px dashed #eee; font-weight:600; color:#c0392b;">9.0, 9.8, 12.5</td></tr>
            <tr style="background:#fdfcfc;"><td style="padding:8px; border-bottom:0;">F</td><td style="padding:8px; border-bottom:0; font-weight:600; color:#c0392b;">20.0, 20.3, 23.4</td><td style="padding:8px; border-bottom:0; font-weight:600; color:#c0392b;">8.7, 9.8, 13.8</td></tr>
        </tbody>
    </table>
    """

    query_rat = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Rat'})
    REMOVE tk.measurements_data
    SET tk.measurements_html = $html
    """
    
    query_dog = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[:HAS_PRECLINICAL_DATA]->(p:PreClinicalData)-[:HAS_TOXICOKINETIC_PARAMETERS]->(tk:ToxicokineticParameters {species: 'Dog'})
    REMOVE tk.measurements_data
    SET tk.measurements_html = $html
    """

    with driver.session() as session:
        session.run(query_rat, html=rat_html)
        session.run(query_dog, html=dog_html)
        print("Set HTML tables for TK Rat and Dog nodes, and removed legacy measurements_data prop.")

if __name__ == "__main__":
    update_tk_nodes_properties_html()
