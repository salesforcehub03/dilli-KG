from flask import Blueprint, render_template, request, jsonify, make_response, session
from services.neo4j_service import get_driver, get_context_for_drug
from services.llm_service import llm_manager
from services.session_service import session_manager
from services.chatbot_agent import get_chatbot_response
from services.tox_predictor import predict_drug_toxicity
from io import BytesIO
import os
import json
import requests

main_bp = Blueprint('main', __name__)

# ===============================
# HOME & VISUALIZATION
# ===============================

@main_bp.route("/")
def home():
    session_manager.clear_session() # Start fresh
    return render_template("index.html")

@main_bp.route("/graph", methods=["GET", "POST"])
def graph():
    if request.method == "POST":
        drug_input = request.form.get("drug")
    else:
        drug_input = request.args.get("drug")
    
    if not drug_input:
        return render_template("index.html")
        
    session_manager.add_visit(drug_input)
    return render_template("graph.html", drug=drug_input)

@main_bp.route("/search_drugs")
def search_drugs():
    query_str = request.args.get("q", "").lower()
    driver = get_driver()
    if not driver:
        return jsonify([])
    
    query = """
    MATCH (d:Drug)
    WHERE toLower(d.drug_name) CONTAINS $q OR d.smiles CONTAINS $q
    RETURN d.drug_name AS name
    LIMIT 10
    """
    try:
        with driver.session() as session:
            result = session.run(query, q=query_str)
            drugs = [record["name"] for record in result if record["name"]]
            return jsonify(list(set(drugs)))
    except Exception as e:
        print(f"Error searching drugs: {e}")
        return jsonify([])

@main_bp.route("/get_graph_data")
def get_graph_data():
    drug_input = request.args.get("drug")
    
    driver = get_driver()
    if not driver:
        # Mock Data (Fallback)
        return jsonify({
            "nodes": [
                {"id": "1", "label": "Drug", "properties": {"name": drug_input or "TestDrug"}},
                {"id": "2", "label": "Drug Product Info", "properties": {"name": "Test Event"}}
            ],
            "edges": [
                {"id": "e1", "from": "1", "to": "2", "label": "HAS_EVENT", "properties": {}}
            ]
        })

    # Graph query: Fetch immediate neighborhood up to 3 hops without artificial isolation 
    # so the user can accurately see how it connects to the class/other drugs.
    query = """
    MATCH (d:Drug)
    WHERE (toLower(d.drug_name) = toLower($drug) OR d.smiles = $drug)
    OPTIONAL MATCH p = (d)-[*1..3]-(n)
    RETURN d, relationships(p) AS r, n
    """
    try:
        with driver.session() as session:
            result = session.run(query, drug=drug_input)
            nodes = []
            edges = []
            processed_nodes = set()
            
            for record in result:
                d = record['d']
                if d.element_id not in processed_nodes:
                    nodes.append({"id": d.element_id, "label": list(d.labels)[0], "properties": dict(d)})
                    processed_nodes.add(d.element_id)
                
                n = record['n']
                if n is not None and n.element_id not in processed_nodes:
                    nodes.append({"id": n.element_id, "label": list(n.labels)[0], "properties": dict(n)})
                    processed_nodes.add(n.element_id)

                path_rels = record['r']
                if path_rels is None:
                    continue
                if isinstance(path_rels, list):
                    for rel in path_rels:
                        # Add intermediate start/end nodes so multi-hop paths are fully represented
                        for intermediate in [rel.start_node, rel.end_node]:
                            if intermediate.element_id not in processed_nodes:
                                nodes.append({"id": intermediate.element_id, "label": list(intermediate.labels)[0], "properties": dict(intermediate)})
                                processed_nodes.add(intermediate.element_id)
                        edges.append({
                            "id": rel.element_id,
                            "from": rel.start_node.element_id,
                            "to": rel.end_node.element_id,
                            "label": rel.type,
                            "properties": dict(rel)
                        })
                else:
                    for intermediate in [path_rels.start_node, path_rels.end_node]:
                        if intermediate.element_id not in processed_nodes:
                            nodes.append({"id": intermediate.element_id, "label": list(intermediate.labels)[0], "properties": dict(intermediate)})
                            processed_nodes.add(intermediate.element_id)
                    edges.append({
                        "id": path_rels.element_id,
                        "from": path_rels.start_node.element_id,
                        "to": path_rels.end_node.element_id,
                        "label": path_rels.type,
                        "properties": dict(path_rels)
                    })
            
            # De-dupe edges
            unique_edges = list({e['id']: e for e in edges}.values())

    except Exception as e:
        print(f"Error executing query: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

    # Enrich sparse Drug nodes from PubChem (outside Neo4j session)
    for node in nodes:
        if node['label'] == 'Drug' and node['properties'].get('drug_name') and not node['properties'].get('smiles'):
            try:
                pubchem = _fetch_pubchem_properties(node['properties']['drug_name'])
                if pubchem:
                    node['properties'].update(pubchem)
            except Exception as e:
                print(f"[PubChem] Error enriching {node['properties'].get('drug_name')}: {e}", flush=True)

    return jsonify({"nodes": nodes, "edges": unique_edges})

@main_bp.route("/get_similar_molecules")
def get_similar_molecules():
    drug_input = request.args.get("drug")

    driver = get_driver()
    if not driver:
        return jsonify({"molecules": []})

    query = """
    MATCH (d:Drug)
    WHERE toLower(d.drug_name) = toLower($drug) OR d.smiles = $drug
    MATCH (d)-[r:SIMILAR_TO]-(sm:Drug)
    WHERE sm.drug_name <> d.drug_name
    RETURN sm, r
    """

    try:
        with driver.session() as session:
            result = session.run(query, drug=drug_input)
            molecules = []
            seen = set()
            for record in result:
                sm = record['sm']
                sm_id = sm.element_id
                if sm_id in seen:
                    continue
                seen.add(sm_id)

                props = dict(sm)
                # Include relationship properties (e.g., similarity_score)
                rel = record.get('r')
                if rel:
                    rel_props = dict(rel) if hasattr(rel, '__iter__') else {}
                    for key in ['similarity_score', 'score', 'similarity']:
                        if key in rel_props:
                            props['similarity_score'] = rel_props[key]
                            break

                molecules.append(props)

        # Enrich sparse molecules from PubChem
        for mol in molecules:
            if not mol.get('smiles'):
                name = mol.get('drug_name') or mol.get('name')
                if name:
                    pubchem = _fetch_pubchem_properties(name)
                    if pubchem:
                        for k, v in pubchem.items():
                            if k not in mol or not mol[k]:
                                mol[k] = v

        return jsonify({"molecules": molecules})

    except Exception as e:
        print(f"Error fetching similar molecules: {e}")
        return jsonify({"molecules": [], "error": str(e)}), 500


@main_bp.route("/get_compare_data")
def get_compare_data():
    """Fetch subnode data for multiple drugs for comparison with path isolation."""
    drugs_input = request.args.get("drugs", "")
    if not drugs_input:
        d1 = request.args.get("drug1")
        d2 = request.args.get("drug2")
        drugs_list = [d1, d2] if (d1 and d2) else []
    else:
        drugs_list = [d.strip() for d in drugs_input.split(",") if d.strip()]

    if not drugs_list:
        return jsonify({"error": "Missing 'drugs' parameter"}), 400
    driver = get_driver()
    if not driver:
        return jsonify({"error": "No database connection"}), 500

    # ISOLATED QUERY: Ensure path stays exactly within the connected context of the specific drug.
    # No class-level bleeding allowed as per user constraint.
    query = """
    MATCH p = (d:Drug)-[*1..6]-(n)
    WHERE (toLower(d.drug_name) CONTAINS toLower($drug) OR d.smiles = $drug)
      AND ALL(node IN nodes(p) WHERE NOT ('Drug' IN labels(node)) OR node = d)
    RETURN d, relationships(p) AS rels, n
    """

    def fetch_drug_data(drug_name):
        nodes = []
        edges = []
        drug_props = {}
        processed_nodes = set()
        processed_edges = set()

        try:
            with driver.session() as session:
                result = session.run(query, drug=drug_name)
                for record in result:
                    d = record['d']
                    if d and d.element_id not in processed_nodes:
                        drug_props = dict(d)
                        nodes.append({"id": d.element_id, "label": list(d.labels)[0], "properties": dict(d)})
                        processed_nodes.add(d.element_id)

                    n = record['n']
                    if n and n.element_id not in processed_nodes:
                        nodes.append({"id": n.element_id, "label": list(n.labels)[0], "properties": dict(n)})
                        processed_nodes.add(n.element_id)

                    rels = record['rels']
                    for rel in rels:
                        if rel.element_id not in processed_edges:
                            edges.append({
                                "id": rel.element_id,
                                "from": rel.start_node.element_id,
                                "to": rel.end_node.element_id,
                                "label": rel.type,
                                "properties": dict(rel)
                            })
                            processed_edges.add(rel.element_id)
                            # Ensure intermediate nodes are in nodes list
                            for inter_node in [rel.start_node, rel.end_node]:
                                if inter_node.element_id not in processed_nodes:
                                    nodes.append({"id": inter_node.element_id, "label": list(inter_node.labels)[0], "properties": dict(inter_node)})
                                    processed_nodes.add(inter_node.element_id)
        except Exception as e:
            print(f"Error fetching compare data for {drug_name}: {e}", flush=True)

        # Map nodes to categories
        category_map = {
            'ClinicalData': ['ClinicalData', 'StudyOverview', 'StudyMetadata', 'PopulationCharacteristics', 'SafetyEfficacy', 'SafetyData', 'EfficacyOutcomes', 'EligibilityCriteria', 'TreatmentManagement', 'SubgroupEfficacy', 'RecommendedDose'],
            'PreclinicalData': ['PreClinicalData', 'PreClinical', 'PreclinicalToxicology', 'PreclinicalData', 'PreclinicalStudy', 'Species'],
            'Transcriptomics': ['TranscriptomicData', 'Signature', 'DifferentialExpression'],
            'ExperimentalDesign': ['ExperimentalDesign', 'ExperimentalGroup', 'DosingAdministration', 'ClinicalChemistryCycle', 'Dose'],
            'Genotoxicity': ['Genotoxicity', 'Carcinogenicity', 'ReproductiveToxicity'],
            'Exposure': ['ExposureMeasurement', 'ToxicokineticMeasurement', 'ToxicokineticParameters', 'Exposure', 'PKData', 'Pharmacokinetics', 'PharmacokineticParameters'],
            'MicroscopicFindings': ['MicroscopicFindings', 'MicroscopicFinding'],
            'AdverseEvents': ['AdverseEvents', 'AdverseEvent', 'Toxicity', 'ToxicityMeasurement']
        }
        
        subnodes = {cat: [] for cat in category_map.keys()}
        subnodes['Other'] = []

        for node in nodes:
            lbl = node['label']
            if lbl == 'Drug': continue
            
            # Clean adverse events to remove unneeded metadata and specific count values
            if lbl == 'AdverseEvent':
                clean_props = {}
                for k, v in node['properties'].items():
                    key_lower = k.lower()
                    if 'count' not in key_lower and key_lower not in ['id', 'uuid', '_id', 'source_id', 'version']:
                        clean_props[k] = v
                node['properties'] = clean_props
            
            found = False
            for cat, labels in category_map.items():
                if lbl in labels:
                    subnodes[cat].append(node['properties'])
                    found = True
                    break
            if not found:
                subnodes['Other'].append(node['properties'])

        # Remove empty categories
        subnodes = {k: v for k, v in subnodes.items() if v}

        # --- OMNIPRESENT AI LAYER (Backfilling DB Gaps + Adding Toxicity Analytics) ---
        from services.llm_service import llm_manager
        from config import Config
        import json
        
        target_cats_toxicity = [
            'Hepatotoxicity Risk',
            'Metabolism & CYP Profile',
            'Preclinical Organ Toxicity',
            'Clinical Safety Alerts',
            'Physicochemical Risk Factors'
        ]
        
        missing_db_categories = [cat for cat in category_map.keys() if cat not in subnodes]
        all_target_cats = missing_db_categories + target_cats_toxicity
        
        if not llm_manager.gemini_key and getattr(Config, 'GEMINI_API_KEY', None):
            llm_manager.update_gemini_key(Config.GEMINI_API_KEY)
            
        prompt = (f"Generate a strictly formatted, professional level clinical and pharmacological analysis for the drug {drug_name}. "
                  f"Output EXACTLY a JSON dictionary featuring these '{len(all_target_cats)}' Categories as keys: {', '.join(all_target_cats)}. "
                  f"For EACH category, provide a list containing AT LEAST 5 to 6 distinct, highly insightful dictionaries. Each dictionary should represent a single specific medical/toxicity observation (e.g., {{'Mechanism': '...', 'Observation': '...', 'Clinical_Significance': '...'}}). "
                  f"The data must be high-density and suitable for professional medical comparison. "
                  f"Do NOT include markdown formatting or blocks, your output will be parsed natively via json.loads().")
                  
        # TIER 1: AZURE GPT-4o (Primary for high-speed synthesis)
        res = llm_manager.query_azure(prompt)
        source_tag = '(Azure GPT-4o Synthesis)'
        
        # TIER 2: GEMINI (Fallback if Azure fails)
        if not res or res.get('status') != 200:
            print(f"[FALLBACK] Azure failed for {drug_name} (Status: {res.get('status') if res else 'No Res'}). Trying Gemini...", flush=True)
            res = llm_manager.query_gemini(prompt)
            source_tag = '(Gemini LLM Synthesis)'

        if res and res.get('status') == 200:
            try:
                reply_text = res['reply'].strip()
                # Secondary cleanup check
                if reply_text.startswith("```json"): reply_text = reply_text[7:]
                elif reply_text.startswith("```"): reply_text = reply_text[3:]
                if reply_text.endswith("```"): reply_text = reply_text[:-3]
                
                ai_data = json.loads(reply_text.strip())
                for cat in all_target_cats:
                    if cat in ai_data and isinstance(ai_data[cat], list):
                        subnodes[cat] = ai_data[cat]
            except Exception as e:
                print(f"LLM omnipresent fallback parse error for {drug_name}: {e}", flush=True)
        # Remove empty categories so UI stays clean if AI misses any
        subnodes = {k: v for k, v in subnodes.items() if v}

        return {
            "name": drug_name,
            "drug_props": drug_props,
            "subnodes": subnodes,
            "nodes": nodes,
            "edges": edges
        }

    from concurrent.futures import ThreadPoolExecutor

    results = {}
    with ThreadPoolExecutor(max_workers=min(len(drugs_list), 6)) as executor:
        # Create a mapping of future to drug name
        futures = []
        for drug in drugs_list:
            futures.append(executor.submit(fetch_drug_data, drug))
            # Staggered start to avoid simultaneous API bursts
            import time
            time.sleep(0.5)
        
        # Results map
        results = {}
        # Wait for all futures in order or as they finish? 
        # Using index mapping to keep results associated with drugs
        for idx, future in enumerate(futures):
            drug = drugs_list[idx]
            try:
                results[drug] = future.result()
            except Exception as e:
                print(f"Parallel fetch failed for {drug}: {e}", flush=True)
                # Ensure we have a placeholder to avoid JS crashes
                results[drug] = {
                    "name": drug,
                    "drug_props": {},
                    "subnodes": {"Error": [{"Message": f"Fetch failed: {e}"}]},
                    "nodes": [],
                    "edges": []
                }

    return jsonify({"compare_results": results, "drugs_list": drugs_list})

def _fetch_pubchem_properties(drug_name):
    """Fetch molecular properties from PubChem by drug name."""
    try:
        # Step 1: Resolve name to CID
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{requests.utils.quote(drug_name)}/cids/JSON"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        cids = resp.json().get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None
        cid = cids[0]

        # Step 2: Fetch properties
        props_url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/"
            "IsomericSMILES,CanonicalSMILES,MolecularWeight,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,IUPACName/JSON"
        )
        resp2 = requests.get(props_url, timeout=10)
        if resp2.status_code != 200:
            return None
        prop_list = resp2.json().get("PropertyTable", {}).get("Properties", [])
        if not prop_list:
            return None
        p = prop_list[0]

        # PubChem may return SMILES under different keys
        smiles = p.get("CanonicalSMILES") or p.get("IsomericSMILES") or p.get("SMILES") or ""

        return {
            "cid": cid,
            "smiles": smiles,
            "molecular_weight": p.get("MolecularWeight", ""),
            "logp": p.get("XLogP", ""),
            "tpsa": p.get("TPSA", ""),
            "h_donor": p.get("HBondDonorCount", ""),
            "h_acceptor": p.get("HBondAcceptorCount", ""),
            "iupac_name": p.get("IUPACName", ""),
        }
    except Exception as e:
        print(f"[PubChem] Lookup failed for {drug_name}: {e}", flush=True)
        return None

# ===============================
# CHATBOT ENDPOINTS
# ===============================

@main_bp.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    drug_input = data.get("drug")
    
    # Delegate to the LangChain Agent
    reply_data = get_chatbot_response(user_message, drug_input)

    # Store in history
    if reply_data.get("status") == 200:
        session_manager.add_chat(drug_input, user_message, reply_data.get("reply"))
    
    return jsonify(reply_data), reply_data.get("status", 200)

@main_bp.route("/predict-toxicity", methods=["POST"])
def predict_toxicity():
    """Drug toxicity prediction endpoint — combines rule-based, molecular, and LLM approaches."""
    data = request.get_json()
    drug_name = data.get("drug")
    if not drug_name:
        return jsonify({"error": "Drug name is required"}), 400
    driver = get_driver()
    if not driver:
        return jsonify({"error": "Graph database not connected"}), 500

    api_key = llm_manager.gemini_key or os.getenv("GEMINI_API_KEY")
    try:
        # Fetch PubChem data for enrichment
        mol_props = _fetch_pubchem_properties(drug_name)
        result = predict_drug_toxicity(drug_name, driver, api_key, mol_props=mol_props)
        return jsonify(result)
    except Exception as e:
        print(f"[ToxPredict] Error: {e}")
        return jsonify({"error": str(e)}), 500



@main_bp.route("/set_key", methods=["POST"])
def set_key():
    data = request.get_json()
    new_key = data.get("key")
    if new_key:
        llm_manager.update_gemini_key(new_key)
        print(f"[INFO] Gemini API Key updated via UI.")
        return jsonify({"status": "success", "message": "API Key updated successfully."})
    return jsonify({"status": "error", "message": "Invalid key"}), 400

@main_bp.route("/track_node", methods=["POST"])
def track_node():
    data = request.get_json()
    node_type = data.get("type", "Unknown")
    label = data.get("label", "")
    properties = data.get("properties", {})
    session_manager.add_node_view(node_type, label, properties)
    return jsonify({"status": "ok"})

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import base64

@main_bp.route("/download_report", methods=["POST"])
def download_report():
    session_data = session_manager.get_session_data()
    data = request.get_json(silent=True) or {}
    graph_image_b64 = data.get("graph_image", "")
    
    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Title
    elements.append(Paragraph("DILI Analysis Session Report", title_style))
    elements.append(Spacer(1, 12))
    
    # Metadata
    elements.append(Paragraph(f"Generated: {session_data['start_time']}", normal_style))
    elements.append(Paragraph(f"Total Drugs Analyzed: {session_data['total_visited']}", normal_style))
    elements.append(Spacer(1, 12))

    # --- GRAPH SNAPSHOT ---
    if graph_image_b64:
        try:
            # Remove header if present (data:image/png;base64,...)
            if "," in graph_image_b64:
                graph_image_b64 = graph_image_b64.split(",")[1]
            
            img_data = base64.b64decode(graph_image_b64)
            img_io = BytesIO(img_data)
            
            # Create Image for ReportLab
            # Constrain width to page width (approx 6 inches)
            img = RLImage(img_io, width=6*inch, height=4*inch, kind='proportional')
            elements.append(Paragraph("Current Visualization Snapshot", heading_style))
            elements.append(Spacer(1, 6))
            elements.append(img)
            elements.append(Spacer(1, 24))
        except Exception as e:
            print(f"Error processing graph image: {e}")
            elements.append(Paragraph(f"Error including graph image: {e}", normal_style))

    # --- DRUGS TABLE ---
    elements.append(Paragraph("Drugs Visited", heading_style))
    elements.append(Spacer(1, 6))

    data = [["Time", "Drug Name"]] # Header
    if session_data['drugs']:
        for item in session_data['drugs']:
            data.append([item['time'], item['name']])
    else:
        data.append(["-", "No drugs analyzed in this session."])

    t = Table(data, colWidths=[100, 400])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))

    # --- NODES EXPLORED ---
    viewed = session_data.get('viewed_nodes', [])
    if viewed:
        elements.append(Paragraph("Nodes Explored", heading_style))
        elements.append(Spacer(1, 6))

        for node in viewed:
            node_block = []
            ntype = node.get('type', 'Node')
            nlabel = node.get('label', '')
            ntime = node.get('time', '')
            node_block.append(Paragraph(f"<b>[{ntime}] {ntype}:</b> {nlabel}", normal_style))

            props = node.get('properties', {})
            if props:
                prop_data = [["Property", "Value"]]
                for k, v in props.items():
                    val_str = str(v) if v is not None else ""
                    if len(val_str) > 120:
                        val_str = val_str[:120] + "..."
                    prop_data.append([Paragraph(f"<b>{k}</b>", normal_style), Paragraph(val_str, normal_style)])

                pt = Table(prop_data, colWidths=[150, 350])
                pt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#34495e")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#ecf0f1")),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                node_block.append(Spacer(1, 4))
                node_block.append(pt)

            node_block.append(Spacer(1, 12))
            elements.append(KeepTogether(node_block))

    # --- CHAT HISTORY ---
    if session_data.get('chat'):
        elements.append(Paragraph("Chat History", heading_style))
        elements.append(Spacer(1, 12))
        
        for chat in session_data['chat']:
            # Use KeepTogether to ensure Q&A stay on same page if possible
            qa_block = []
            qa_block.append(Paragraph(f"<b>[{chat['time']}] Q:</b> {chat['question']}", normal_style))
            qa_block.append(Spacer(1, 4))
            qa_block.append(Paragraph(f"<b>A:</b> {chat['answer']}", normal_style))
            qa_block.append(Spacer(1, 12))
            elements.append(KeepTogether(qa_block))
    
    # Footer
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Generated by DILI Analysis Platform", normal_style))
    
    # Build PDF
    doc.build(elements)
    
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=dili_session_report.pdf'
    return response
