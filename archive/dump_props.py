from services.neo4j_service import driver

def dump_all_properties(drug_name):
    """Dumps all properties for all nodes/subnodes linked to a drug, max depth 5."""
    query = """
    MATCH (d:Drug {drug_name: $drug})-[*0..5]->(n)
    RETURN labels(n)[0] AS label, properties(n) AS props
    """
    with open('belinostat_all_props.txt', 'w', encoding='utf-8') as f:
        import json
        seen = set()
        with driver.session() as session:
            result = list(session.run(query, drug=drug_name))
            f.write(f"Total paths: {len(result)}\n\n")
            for rec in result:
                lbl = rec['label']
                props = dict(rec['props'])
                # Filter out HTML and None
                clean_props = {k: v for k, v in props.items() if v is not None and k != 'measurements_html'}
                key = lbl + str(sorted(clean_props.keys()))
                if key in seen:
                    continue
                seen.add(key)
                f.write(f"=== {lbl} ===\n")
                f.write(f"Keys: {list(clean_props.keys())}\n")
                # Show first record sample
                sample = {k: str(v)[:80] for k, v in clean_props.items()}
                f.write(f"Sample: {json.dumps(sample, indent=2)}\n\n")
    print("Done - see belinostat_all_props.txt")

dump_all_properties('Belinostat')
