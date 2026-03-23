---
description: How to run the DILI Analysis Platform
---

Follow these steps to start the application and load essential data.

### 1. Start the Application Server
Run the main Flask application to enable the Graph UI and Chatbot.
```powershell
# Activate the virtual environment
.\venv\Scripts\activate

# Start the server
python app.py
```
*Access the app at: [http://localhost:5000](http://localhost:5000)*

### 2. Load Preclinical Data (Optional)
If you need to refresh the knowledge graph with new Rat or Dog Toxicokinetic data, run these from the `scripts/` folder:
```powershell
# Load Rat TK Data
python scripts/add_rat_tk_data.py

# Load Dog TK Data
python scripts/add_dog_tk_data.py
```

### 3. Maintenance Scripts
- **Update Graph**: `python scripts/update_graph.py` (Re-processes graph relationships)
- **Format UI**: `python scripts/format_tk_html.py` (Updates the visual templates for TK data)
