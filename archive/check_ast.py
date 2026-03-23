import sys, codecs
sys.path.insert(0, '.')
from services.neo4j_service import driver

def run(q):
    with driver.session() as s:
        rows = list(s.run(q))
        return [{k: r[k] for k in r.keys()} for r in rows if hasattr(r, 'keys')]

results = {}

# Check ClinicalData for Vorinostat - does cmax property have a value?
results['clinical_cmax'] = run("""
MATCH (d:Drug)-[:HAS_CLINICAL_DATA]->(c)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN c.cmax, c.dose_level, c.study_id LIMIT 5
""")

# Check all properties with alt/ast
results['alt_ast_in_clinical'] = run("""
MATCH (d:Drug)-[:HAS_CLINICAL_DATA]->(c)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN c.alt_elevation, c.ast_elevation, c.bilirubin_elevation LIMIT 5
""")

# Check adverse events structure
results['adverse_events'] = run("""
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_container)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
MATCH (ae_container)-[r]->(n)
RETURN type(r), labels(n), keys(n) LIMIT 10
""")

# Try to find AdverseEvent nodes
results['ae_nodes'] = run("""
MATCH (d:Drug)-[*1..4]-(ae:AdverseEvent)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN ae LIMIT 10
""")

# Check what's in the adverse events container
results['ae_container'] = run("""
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN labels(ae_c), keys(ae_c), ae_c LIMIT 3
""")

# Deep search for any node mentioning ALT/AST
results['alt_deep'] = run("""
MATCH (d:Drug)-[*1..5]-(n)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
WITH n, keys(n) as k
WHERE any(key IN k WHERE toLower(toString(key)) CONTAINS 'alt' OR toLower(toString(key)) CONTAINS 'ast' OR toLower(toString(key)) CONTAINS 'liver')
RETURN labels(n), k, n LIMIT 10
""")

with codecs.open('ast_diag.txt', 'w', encoding='utf-8') as f:
    import json
    for k, v in results.items():
        f.write(f"\n=== {k} ===\n")
        for row in v:
            try:
                f.write(json.dumps(row, default=str) + "\n")
            except:
                f.write(str(row) + "\n")

print("Done -> ast_diag.txt")
