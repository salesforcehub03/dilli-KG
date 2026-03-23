from services.neo4j_service import driver
def count_unfiltered():
    query = """
    MATCH (d:Drug {drug_name: 'Belinostat'})-[r*1..4]-(n)
    RETURN count(distinct n) as nodes
    """
    with driver.session() as session:
        print(session.run(query).single()['nodes'])
if __name__ == "__main__": count_unfiltered()
