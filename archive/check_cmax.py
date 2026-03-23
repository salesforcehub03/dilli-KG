import sys
sys.path.insert(0, '.')
from services.neo4j_service import driver

def run(q):
    with driver.session() as s:
        rows = list(s.run(q))
        out = []
        for r in rows:
            if hasattr(r, 'keys'):
                out.append({k: r[k] for k in r.keys()})
            else:
                out.append(str(r))
        return out

results = {}

# Direct connections from drug
results['direct'] = run("""
MATCH (d:Drug)-[rel]->(n)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN type(rel) as t, labels(n) as lbl, keys(n) as k
""")

# Pharmacokinetics node content
results['pk'] = run("""
MATCH (d:Drug)-[:HAS_PHARMACOKINETICS]->(pk)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN pk LIMIT 3
""")

# Preclinical tox deeper
results['tox'] = run("""
MATCH (d:Drug)-[:HAS_PRECLINICAL_TOXICOLOGY]->(p)-[r1]->(m)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN type(r1) as r, labels(m) as lbl, keys(m) as k LIMIT 10
""")

# ToxicoKineticMeasurement content
results['tox_measure'] = run("""
MATCH (d:Drug)-[*1..6]-(n:ToxicokineticMeasurement)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN n LIMIT 5
""")

# ToxicoKineticParameters content
results['tox_params'] = run("""
MATCH (d:Drug)-[*1..6]-(n:ToxicokineticParameters)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN n LIMIT 5
""")

# Exposure content
results['exposure'] = run("""
MATCH (d:Drug)-[*1..6]-(n:Exposure)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN n LIMIT 5
""")

# ExposureMeasurement content
results['exposure_m'] = run("""
MATCH (d:Drug)-[*1..6]-(n:ExposureMeasurement)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN n LIMIT 5
""")

# PreclinicalStudy content
results['prec_study'] = run("""
MATCH (d:Drug)-[*1..6]-(n:PreclinicalStudy)
WHERE toLower(d.drug_name) = toLower('Vorinostat')
RETURN n LIMIT 5
""")

import json, codecs
with codecs.open('cmax_diag2.txt', 'w', encoding='utf-8') as f:
    for k, v in results.items():
        f.write(f"\n=== {k} ===\n")
        for row in v:
            f.write(str(row) + "\n")

print("Done. Output written to cmax_diag2.txt")
