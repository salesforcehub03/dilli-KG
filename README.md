# Drug Knowledge Graph App

This is a Flask application that visualizes drug data from a Neo4j database and provides a chatbot interface.

## Setup

1.  **Install Requirements**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file in the root directory with your Neo4j credentials:
    ```
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_password_here
    ```

3.  **Run the App**:
    ```bash
    python app.py
    ```

4.  **Open in Browser**:
    Go to [http://localhost:5000](http://localhost:5000).

## Features

- **Graph Visualization**: View relationships between drugs, adverse events, and other entities.
- **Chatbot**: Ask natural language questions about the drug data.
