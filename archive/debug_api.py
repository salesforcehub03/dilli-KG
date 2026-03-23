import urllib.request
import json

url = "http://localhost:10000/get_graph_data?drug=Belinostat"
response = urllib.request.urlopen(url, timeout=30)
data = json.loads(response.read())

nodes = data.get('nodes', [])
edges = data.get('edges', [])

# Count by label
from collections import Counter
labels = Counter(n['label'] for n in nodes)

with open('api_response_check.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total nodes: {len(nodes)}\n")
    f.write(f"Total edges: {len(edges)}\n\n")
    f.write("Node label counts:\n")
    for lbl, cnt in sorted(labels.items(), key=lambda x: -x[1]):
        f.write(f"  {lbl}: {cnt}\n")

print(f"Written api_response_check.txt — {len(nodes)} total nodes")
