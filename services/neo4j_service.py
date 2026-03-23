from neo4j import GraphDatabase
import requests
import json
from config import Config

class Neo4jHTTPDriver:
    """Custom HTTP Driver for Aura Query API v2 when Bolt fails."""
    def __init__(self, uri, user, password):
        self.uri = uri
        self.auth = (user, password)
        self.headers = {
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json"
        }
    
    def verify_connectivity(self):
        payload = {"statement": "RETURN 1"}
        try:
            response = requests.post(self.uri, json=payload, auth=self.auth, headers=self.headers, timeout=5)
            if response.status_code in [200, 202]:
                print(f"[SUCCESS] HTTP API Connection Verified.")
                return True
            else:
                raise Exception(f"HTTP Error {response.status_code}: {response.text}")
        except Exception as e:
            raise e

    def session(self):
        return Neo4jHTTPSession(self.uri, self.auth, self.headers)

    def close(self):
        pass

class Neo4jHTTPSession:
    def __init__(self, uri, auth, headers):
        self.uri = uri
        self.auth = auth
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def run(self, query, **kwargs):
        payload = {"statement": query, "parameters": kwargs}
        response = requests.post(self.uri, json=payload, auth=self.auth, headers=self.headers)
        if response.status_code not in [200, 202]:
            raise Exception(f"Query failed: {response.text}")
        return Neo4jHTTPResult(response.json())

class Neo4jHTTPResult:
    def __init__(self, data):
        self.fields = data.get("data", {}).get("fields", [])
        self.values = data.get("data", {}).get("values", [])
        self.idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx < len(self.values):
            row = self.values[self.idx]
            self.idx += 1
            return self._process_row(row)
        raise StopIteration
        
    def single(self):
        if self.values:
             return self._process_row(self.values[0])
        return None

    def _process_row(self, row):
        processed_row = {}
        for field, value in zip(self.fields, row):
            processed_row[field] = self._wrap_value(value)
        return processed_row
    
    def _wrap_value(self, value):
        if isinstance(value, dict):
             return tuple_shim(value)
        elif isinstance(value, list):
             return [self._wrap_value(v) for v in value]
        return value

class tuple_shim(dict):
    def __init__(self, data):
        super().__init__(data.get("properties", data))
        self._data = data
        self.element_id = data.get("elementId", data.get("id", "unknown"))
        self.labels = data.get("labels", [])
        self.type = data.get("type", "UNKNOWN")
        self.start_node = simple_node_ref(data.get("startNodeElementId"))
        self.end_node = simple_node_ref(data.get("endNodeElementId"))

class simple_node_ref:
    def __init__(self, eid):
        self.element_id = eid 

def _create_driver():
    uri = Config.NEO4J_URI
    user = Config.NEO4J_USER
    password = Config.NEO4J_PASSWORD

    # 1. HTTP API (if explicit)
    if "query/v2" in uri:
        print(f"[INFO] Using HTTP API Driver for {uri}")
        try:
            driver = Neo4jHTTPDriver(uri, user, password)
            driver.verify_connectivity()
            return driver
        except Exception as e:
            print(f"[ERROR] HTTP Driver failed: {e}")
            return None

    # 2. Bolt Driver
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5.0)
        driver.verify_connectivity()
        print(f"[SUCCESS] Connected to Neo4j via Bolt.")
        return driver
    except Exception as e:
        print(f"[WARNING] Bolt failed: {e}. Attempting HTTP Fallback...")
    
    # 3. HTTP Fallback (Derived)
    if "databases.neo4j.io" in uri:
        try:
            host = uri.split("://")[1]
            http_url = f"https://{host}/db/neo4j/query/v2"
            print(f"[INFO] Derived HTTP URL: {http_url}")
            driver = Neo4jHTTPDriver(http_url, user, password)
            driver.verify_connectivity()
            return driver
        except Exception as e:
            print(f"[ERROR] HTTP Fallback failed: {e}")

    return None

# Global driver instance (Lazy Loaded)
_driver = None

def get_driver():
    """Returns the Neo4j driver, initializing it if necessary."""
    global _driver
    if _driver is None:
        _driver = _create_driver()
    return _driver

def get_context_for_drug(drug_input):
    """Retrieve structured graph context for a drug."""
    driver = get_driver()
    if not driver:
        return "Graph database not connected."
        
    query = """
    MATCH (d:Drug)
    WHERE toLower(d.drug_name) = toLower($drug) OR d.smiles = $drug
    OPTIONAL MATCH (d)-[:HAS_ADVERSE_EVENTS]->(:AdverseEvents)-[:HAS_EVENT]->(ae)
    OPTIONAL MATCH (d)-[:HAS_SAFETY_EFFICACY]->(:SafetyEfficacy)-[:HAS_SAFETY_DATA]->(sd)
    OPTIONAL MATCH (d)-[:HAS_PRECLINICAL_DATA]->(:PreClinicalData)-[:HAS_MECHANISM_OF_ACTION]->(moa)
    RETURN d, collect(DISTINCT ae.name) AS adverse_events,
           sd, moa
    """
    try:
        with driver.session() as session:
            result = session.run(query, drug=drug_input)
            record = result.single()

        if record and record["d"]:
            d_props = dict(record["d"])
            events = record["adverse_events"]
            sd = dict(record["sd"]) if record["sd"] else {}
            moa = dict(record["moa"]) if record["moa"] else {}
            
            return f"""
            Drug Info: {json.dumps(d_props)}
            Adverse Events: {', '.join(events[:20])}
            Safety Data: {json.dumps(sd)}
            Mechanism of Action: {json.dumps(moa)}
            """
    except Exception as e:
        print(f"Error fetching context: {e}")
        return f"Error fetching graph data: {e}"
        
    return "No specific graph data found."
