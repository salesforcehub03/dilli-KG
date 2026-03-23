from services.neo4j_service import driver

def trace_deep_paths(drug_name, output):
    """Trace exact path depth to Signature and DifferentialExpression from search drug."""
    targets = ['Signature', 'DifferentialExpression', 'TranscriptomicData']
    for target in targets:
        for depth in [2, 3, 4, 5, 6]:
            query = f"""
            MATCH path = (d:Drug {{drug_name: $drug}})-[*1..{depth}]->(n:{target})
            RETURN count(n) as cnt
            """
            with driver.session() as session:
                result = session.run(query, drug=drug_name).single()
                cnt = result['cnt']
                output.write(f"  {drug_name} -> {target} at depth 1..{depth}: {cnt} nodes\n")
            if cnt > 0:
                break

with open('deep_path_trace.txt', 'w', encoding='utf-8') as f:
    for drug in ['Belinostat', 'Vorinostat', 'Dacinostat']:
        f.write(f"\n=== {drug} ===\n")
        trace_deep_paths(drug, f)
print("Written to deep_path_trace.txt")
