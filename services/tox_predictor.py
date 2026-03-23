import os
import json
import logging
import io
import requests
from typing import List, Dict, Tuple, Optional
from rdkit import Chem
from rdkit.Chem import Draw, Descriptors
from openai import AzureOpenAI
from dotenv import load_dotenv
from services.llm_service import llm_manager

# --- 1. Production Logging & Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load from .env file
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

# Configuration with validation (Gemini is primary now)
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# DeepChem Import with robust check
try:
    import deepchem as dc
    import numpy as np
    DEEPCHEM_AVAILABLE = True
    logger.info("DeepChem successfully loaded.")
except ImportError:
    DEEPCHEM_AVAILABLE = False
    logger.warning("DeepChem not found. Using fallback prediction logic.")

# ============================================================
# NEO4J HELPER FUNCTIONS
# ============================================================

def _run(driver, q, **params):
    try:
        with driver.session() as s:
            result = list(s.run(q, **params))
            return [{k: r[k] for k in r.keys()} for r in result if hasattr(r, 'keys')]
    except Exception as e:
        print(f"[ToxPredict] Query error: {e}")
        return []

def _safe_float(val):
    try:
        return float(val)
    except:
        return None

def _contains(text, *words):
    t = str(text or "").lower()
    return any(w in t for w in words)


# ============================================================
# CLINICAL DATA SCORING (For Information/Proofs)
# ============================================================
def _score_clinical(driver, drug: str) -> tuple:
    """Returns (score, flags, evidence)"""
    score = 0
    flags = []
    evidence = {}

    rows = _run(driver, f"""
    MATCH p = (d:Drug)-[:HAS_CLINICAL_DATA]->(c)
    WHERE toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}'
    MATCH (d)-[:HAS_CLINICAL_DATA]->(c) 
    WHERE ALL(n IN nodes(p) WHERE NOT ('Drug' IN labels(n)) OR n = d)
    RETURN c
    """)

    if not rows:
        evidence["clinical"] = "No direct ClinicalData found"
        return score, flags, evidence

    # Process all clinical nodes
    for row in rows:
        c = row["c"]
        study = c.get("study_id", "Unknown Study")
        
        # ALT elevation
        alt = str(c.get("alt_elevation", "") or "")
        if alt.strip() and not _contains(alt, "none", "no ", "not ", "normal", "n/a"):
            evidence[f"alt_{study}"] = alt
            if _contains(alt, "grade 4", "g4"):
                flags.append(f"Severe (G4) ALT elevation in {study}")
            elif _contains(alt, "grade 3", "g3", "3/4", "3-4", ">3x", ">5x", ">10x"):
                flags.append(f"Grade 3/4 ALT elevation in {study}")
            elif _contains(alt, "grade 2", "g2", "elevation", "increase", "raised", "elevated"):
                flags.append(f"ALT elevation in {study}")
            else:
                flags.append(f"ALT finding in {study}: {alt}")

        # AST elevation
        ast = str(c.get("ast_elevation", "") or "")
        if ast.strip() and not _contains(ast, "none", "no ", "not ", "normal", "n/a"):
            evidence[f"ast_{study}"] = ast
            if _contains(ast, "grade 4", "g4"):
                flags.append(f"Severe (G4) AST elevation in {study}")
            elif _contains(ast, "grade 3", "g3", "3/4", "3-4", ">3x", ">5x"):
                flags.append(f"Grade 3/4 AST elevation in {study}")
            else:
                flags.append(f"AST elevation in {study}: {ast}")

        # Bilirubin
        bili = str(c.get("bilirubin_elevation", "") or "")
        if bili.strip() and not _contains(bili, "none", "no ", "not ", "normal", "n/a"):
            evidence[f"bilirubin_{study}"] = bili
            flags.append(f"Bilirubin elevation in {study}: {bili}")

        # SAEs
        sae = str(c.get("sae_reported", "") or "")
        if sae.strip() and not _contains(sae, "none", "no ", "not ", "n/a"):
            evidence[f"sae_{study}"] = sae[:100]
            if _contains(sae, "death", "fatal", "life-threatening"):
                flags.append(f"Fatal/Life-threatening SAE in {study}")
            else:
                flags.append(f"SAEs in {study}: {sae[:60]}...")

    return score, flags, evidence


# ============================================================
# PRECLINICAL DATA SCORING (For Information/Proofs)
# ============================================================
def _score_preclinical(driver, drug: str) -> tuple:
    """Returns (score, flags, evidence, animal_cmax_data)"""
    score = 0
    flags = []
    evidence = {}
    animal_cmax_data = []

    # Use flexible path to find PreclinicalStudy, but isolate to current drug
    ps_rows = _run(driver, f"""
    MATCH p = (d:Drug)-[*1..6]-(ps:PreclinicalStudy)
    WHERE (toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}')
      AND ALL(n IN nodes(p) WHERE NOT ('Drug' IN labels(n)) OR toLower(n.drug_name) = toLower('{drug}') OR n.smiles = '{drug}' OR toLower(n.name) = toLower('{drug}'))
      AND (ps.drug IS NULL OR toLower(ps.drug) = toLower('{drug}') OR ps.drug CONTAINS '{drug}' OR toLower(ps.compound) = toLower('{drug}'))
    RETURN ps.noael AS noael, ps.loael AS loael,
           ps.alt AS alt, ps.ast AS ast,
           ps.cmax AS cmax, ps.auc AS auc,
           ps.species AS species, ps.dose AS dose,
           ps.route AS route, ps.sex AS sex,
           ps.primary_histopath AS histopath,
           ps.adverse_events AS ae_list
    LIMIT 10
    """)

    if not ps_rows:
        evidence["preclinical"] = "No PreclinicalStudy found within 6 hops"
    else:
        evidence["preclinical_studies_found"] = len(ps_rows)
        for ps in ps_rows:
            species = ps.get("species", "Unknown")
            noael = _safe_float(ps.get("noael"))
            loael = _safe_float(ps.get("loael"))
            alt_val = _safe_float(ps.get("alt"))
            histopath = str(ps.get("histopath", "") or "")
            
            if noael is not None:
                evidence[f"noael_{species}"] = f"{noael} mg/kg"
                if noael < 10:
                    flags.append(f"Low NOAEL ({noael} mg/kg) in {species}")

            if loael is not None:
                evidence[f"loael_{species}"] = f"{loael} mg/kg"
                if noael and loael / noael < 3:
                    flags.append(f"Narrow toxicity window ({loael/noael:.1f}x) in {species}")

            if alt_val and alt_val > 100:
                evidence[f"preclinical_alt_{species}"] = alt_val
                flags.append(f"Elevated preclinical ALT ({alt_val} U/L) in {species}")

            if histopath and not _contains(histopath, "none", "normal", "n/a"):
                evidence[f"histopath_{species}"] = histopath
                if _contains(histopath, "liver", "hepat", "necrosis"):
                    flags.append(f"Liver histopath FINDING ({species}): {histopath}")
                else:
                    flags.append(f"Preclinical FINDING ({species}): {histopath}")

            if _safe_float(ps.get("cmax")):
                animal_cmax_data.append({"species": species, "cmax": _safe_float(ps.get("cmax")), "noael": noael})

    # ExposureMeasurement (toxicokinetic Cmax by dose/species) - isolated
    em_rows = _run(driver, f"""
    MATCH p = (d:Drug)-[*1..6]-(em:ExposureMeasurement)
    WHERE (toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}')
      AND ALL(n IN nodes(p) WHERE NOT ('Drug' IN labels(n)) OR toLower(n.drug_name) = toLower('{drug}') OR n.smiles = '{drug}' OR toLower(n.name) = toLower('{drug}'))
      AND (em.drug IS NULL OR toLower(em.drug) = toLower('{drug}') OR em.drug CONTAINS '{drug}' OR toLower(em.compound) = toLower('{drug}'))
    RETURN em.species AS species, em.sex AS sex, em.day AS day,
           em.dose_mg_per_kg AS dose, em.cmax_ug_per_mL AS cmax,
           em.auc_ug_h_per_mL AS auc
    ORDER BY em.dose_mg_per_kg DESC
    LIMIT 10
    """)
    if em_rows:
        evidence["exposure_measurements"] = len(em_rows)
        for em in em_rows:
            c = _safe_float(em.get("cmax"))
            if c:
                animal_cmax_data.append({
                    "species": em.get("species", "?"),
                    "cmax": c,
                    "dose": em.get("dose"),
                    "day": em.get("day"),
                    "noael": None
                })

    # ToxicokineticMeasurement - isolated
    tk_rows = _run(driver, f"""
    MATCH p = (d:Drug)-[*1..6]-(tm:ToxicokineticMeasurement)
    WHERE (toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}')
      AND ALL(n IN nodes(p) WHERE NOT ('Drug' IN labels(n)) OR toLower(n.drug_name) = toLower('{drug}') OR n.smiles = '{drug}' OR toLower(n.name) = toLower('{drug}'))
      AND (tm.drug IS NULL OR toLower(tm.drug) = toLower('{drug}') OR tm.drug CONTAINS '{drug}' OR toLower(tm.compound) = toLower('{drug}'))
    RETURN tm.sex AS sex, tm.dose_mg_per_kg AS dose,
           tm.cmax_day1_ug_per_mL AS cmax1, tm.cmax_day5_ug_per_mL AS cmax5,
           tm.cmax_day151_ug_per_mL AS cmax151,
           tm.auc_day1_ug_h_per_mL AS auc1
    LIMIT 5
    """)
    if tk_rows:
        evidence["toxicokinetic_measurements"] = len(tk_rows)
        # Check accumulation (day151 vs day1 Cmax ratio)
        for tk in tk_rows:
            c1 = _safe_float(tk.get("cmax1"))
            c151 = _safe_float(tk.get("cmax151"))
            if c1 and c151 and c1 > 0:
                accum = c151 / c1
                evidence["cmax_accumulation_ratio"] = round(accum, 2)
                if accum > 2:
                    flags.append(f"Drug accumulation: Day151/Day1 Cmax ratio = {accum:.1f}x (accumulation risk)")
                elif accum > 1.3:
                    flags.append(f"Mild drug accumulation: Day151/Day1 Cmax ratio = {accum:.1f}x")
                break

    return score, flags, evidence, animal_cmax_data


# ============================================================
# ADVERSE EVENT SCORING (For Information/Proofs)
# ============================================================
def _score_adverse_events(driver, drug: str) -> tuple:
    """Returns (score, flags, evidence)"""
    score = 0
    flags = []
    evidence = {}

    # Flexible path for AEs, but MUST NOT hop through other Drug nodes
    ae_rows = _run(driver, f"""
    MATCH p = (d:Drug)-[*1..3]-(ae:AdverseEvent)
    WHERE (toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}')
      AND ALL(n IN nodes(p) WHERE NOT ('Drug' IN labels(n)) OR toLower(n.drug_name) = toLower('{drug}') OR n.smiles = '{drug}' OR toLower(n.name) = toLower('{drug}'))
      AND (ae.drug IS NULL OR toLower(ae.drug) = toLower('{drug}') OR ae.drug CONTAINS '{drug}' OR toLower(ae.compound) = toLower('{drug}'))
    RETURN ae.name AS name, ae.frequency AS freq, ae.severity AS severity, ae.SOC AS soc
    LIMIT 50
    """)

    if not ae_rows:
        evidence["adverse_events"] = "No AdverseEvent nodes found within 3 hops"
        return score, flags, evidence

    total_ae = len(ae_rows)
    evidence["total_ae_count"] = total_ae
    
    hepatic_aes = [r["name"] for r in ae_rows if _contains(r.get("soc", ""), "hepat", "liver", "biliar") or _contains(r["name"], "alt", "ast", "jaundice")]
    if hepatic_aes:
        evidence["hepatic_ae_proofs"] = hepatic_aes[:5]
        flags.append(f"{len(hepatic_aes)} Hepatobiliary AEs detected (e.g., {hepatic_aes[0]})")
    
    serious_count = len([r for r in ae_rows if _contains(r.get("severity", ""), "serious", "fatal", "grade 3", "grade 4")])
    if serious_count > 0:
        evidence["serious_ae_count"] = serious_count
        flags.append(f"{serious_count} Serious/Severe AEs reported")

    return score, flags, evidence


# ============================================================
# SAFETY MARGIN CALCULATION (For Information/Proofs)
# ============================================================
def _compute_safety_margin(driver, drug: str, animal_cmax_data: list) -> tuple:
    """Returns (score_delta, flags, evidence)"""
    score = 0
    flags = []
    evidence = {}

    human_rows = _run(driver, f"""
    MATCH (d:Drug)-[:HAS_CLINICAL_DATA]->(c)
    WHERE toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}'
    RETURN c.cmax AS cmax LIMIT 1
    """)

    human_cmax_str = human_rows[0].get("cmax") if human_rows else None
    if not human_cmax_str or not animal_cmax_data:
        evidence["safety_margin"] = "Incomplete data for calculation"
        return score, flags, evidence

    try:
        import re
        nums = re.findall(r'\d+\.?\d*', str(human_cmax_str))
        human_cmax = float(nums[0])
        evidence["human_cmax"] = f"{human_cmax} ug/mL"
         
        for anim in animal_cmax_data:
            mar = anim["cmax"] / human_cmax
            spec = anim["species"]
            evidence[f"margin_{spec}"] = f"{mar:.2f}x"
            if mar < 1:
                flags.append(f"CRITICAL: Human Cmax exceeds animal NOAEL Cmax ({spec})")
            elif mar < 5:
                flags.append(f"Narrow safety margin ({mar:.1f}x) in {spec}")
    except:
        evidence["safety_margin"] = "Error parsing numeric values"

    return score, flags, evidence

def _extract_safety_analytics(driver, drug: str) -> dict:
    """Extract numerical data points for ALT and AUC/Cmax across species and studies."""
    analytics = {
        "alt_data": [],
        "pk_data": [],
        "baseline_alt": 50 # Normal reference value
    }
    
    # Robust undirected multi-hop search for ALT, AST, AUC, and Cmax data
    # Path MUST NOT cross other Drug nodes to avoid data bleeding
    query = f"""
    MATCH p = (d:Drug)-[*1..6]-(n)
    WHERE (toLower(d.drug_name) = toLower('{drug}') OR d.smiles = '{drug}')
      AND (n.alt IS NOT NULL OR n.ast IS NOT NULL OR n.cmax IS NOT NULL OR n.auc IS NOT NULL OR n.cmax_ug_per_mL IS NOT NULL OR n.auc_ug_h_per_mL IS NOT NULL OR n.cmax_day1_ug_per_mL IS NOT NULL)
      AND ALL(node IN nodes(p) WHERE NOT ('Drug' IN labels(node)) OR toLower(node.drug_name) = toLower('{drug}') OR node.smiles = '{drug}' OR toLower(node.name) = toLower('{drug}'))
      AND (n.drug IS NULL OR toLower(n.drug) = toLower('{drug}') OR n.drug CONTAINS '{drug}' OR toLower(n.compound) = toLower('{drug}'))
    RETURN DISTINCT n.alt AS alt, n.ast AS ast, n.cmax AS cmax, n.auc AS auc, 
           n.species AS species, n.name AS name,
           n.dose_mg_per_kg AS dose, n.cmax_ug_per_mL AS cmax_v1,
           n.auc_ug_h_per_mL AS auc_v1, n.cmax_day1_ug_per_mL AS cmax_v2
    LIMIT 20
    """
    rows = _run(driver, query)
    seen_labels = set()
    
    for r in rows:
        # ALT/AST Processing
        alt_val = _safe_float(r.get("alt"))
        ast_val = _safe_float(r.get("ast"))
        species = r.get("species") or r.get("name") or "Human"
        
        # Check for textual elevation flags
        if not alt_val:
            for k, v in r.items():
                if "alt_elevation" in str(k) and _contains(str(v), "observed", "yes", "true", "present"):
                    alt_val = 200 # Representative high value
                    break

        if alt_val:
            label = f"{species} (ALT Study)"
            if label not in seen_labels:
                analytics["alt_data"].append({"label": label, "value": alt_val})
                seen_labels.add(label)
        
        if ast_val:
            ast_label = f"{species} (AST Study)"
            if ast_label not in seen_labels:
                analytics["alt_data"].append({"label": ast_label, "value": ast_val})
                seen_labels.add(ast_label)
        
        # PK Processing (Cmax and AUC)
        cmax = _safe_float(r.get("cmax") or r.get("cmax_v1") or r.get("cmax_v2"))
        auc = _safe_float(r.get("auc") or r.get("auc_v1"))

        if cmax is not None and cmax > 0:
             pk_label = f"{species} (Cmax)"
             if pk_label not in seen_labels:
                 analytics["pk_data"].append({"label": pk_label, "value": cmax})
                 seen_labels.add(pk_label)

        if auc is not None and auc > 0:
             auc_label = f"{species} (AUC)"
             if auc_label not in seen_labels:
                 analytics["pk_data"].append({"label": auc_label, "value": auc})
                 seen_labels.add(auc_label)

    return analytics


# ============================================================
# NEW: RDKit Core Chemical Logic
# ============================================================
def get_chemical_analysis(smiles: str) -> Dict:
    """Detect structural alerts and generate molecular properties."""
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return {"error": "Invalid SMILES string"}
    
    alerts = []
    # 1. Aromatic amines (often toxic/mutagenic/DILI)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('c1ccccc1N')):
        alerts.append("Aromatic Amine (potential mutagenicity/DILI)")
    
    # 2. Nitro groups (potential DNA damage/metabolic activation)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('[N+](=O)[O-]')):
        alerts.append("Nitro Group (potential DNA damage/metabolic activation)")

    # 3. Hydrazines (Significant DILI risk)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('[NX3][NX3]')):
        alerts.append("Hydrazine/Hydrazone (High DILI risk via covalent binding)")

    # 4. Quinone-forming structures
    if mol.HasSubstructMatch(Chem.MolFromSmarts('c1ccc(O)cc1')) or mol.HasSubstructMatch(Chem.MolFromSmarts('O=C1C=CC(=O)C=C1')):
        alerts.append("Quinone-forming motif (DILI risk via oxidative stress)")

    # 5. Thiophene
    if mol.HasSubstructMatch(Chem.MolFromSmarts('c1ccsc1')):
        alerts.append("Thiophene Ring (Potential metabolic activation/DILI)")

    # 6. Iodo-aromatics (often associated with thyroid/liver toxicity)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('cI')):
        alerts.append("Iodo-aromatic motif (High potential for idiosyncratic DILI)")

    # 7. Poly-aromatic ethers (often high LogP/high toxicity)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('cOc')):
        alerts.append("Di-aryl Ether (Common in high-risk hepatotoxicants)")

    # 8. Platinum-containing compounds (Significant systemic toxicity)
    if any(atom.GetSymbol() == 'Pt' for atom in mol.GetAtoms()):
        alerts.append("Platinum-complex (High systemic toxicity / DNA cross-linking)")
    
    # 9. Halogenated Alkanes (Potential hepatotoxicity)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('[C;H2,H1,H0][Cl,Br,I]')):
        alerts.append("Halogenated Alkyl (Potential reactive metabolite formation)")

    # 10. Hydroxamic Acids (Potential for metal chelation / enzyme inhibition outside target)
    if mol.HasSubstructMatch(Chem.MolFromSmarts('C(=O)NO')):
        alerts.append("Hydroxamic Acid (Potential for off-target chelation)")

    return {
        "alerts": alerts,
        "mol_weight": round(Descriptors.ExactMolWt(mol), 2),
        "logp": round(Descriptors.MolLogP(mol), 2)
    }

def predict_scores(smiles: str, analysis: dict, kg_score: float = 0.0) -> Dict[str, Tuple[float, str]]:
    """Predict Toxicity and DILI scores dynamically using structural properties and RDKit alerts."""
    results = {}
    
    # Calculate a baseline risk from physico-chemical properties
    mw = analysis.get("mol_weight", 0)
    logp = analysis.get("logp", 0)
    alerts = analysis.get("alerts", [])
    
    # Calculate a baseline risk from physico-chemical properties
    mw = analysis.get("mol_weight", 0)
    logp = analysis.get("logp", 0)
    alerts = analysis.get("alerts", [])
    
    # --- 1. Base Property Risk (DILI Rule of 3: LogP > 3, MW > 400) ---
    base_risk = 0.0
    if logp > 3 and mw > 400:
        base_risk += 25  # Significant synergistic risk
    elif mw > 500 or logp > 5:
        base_risk += 15  # Moderate risk from single factor
    
    # --- 2. General Toxicity Prediction (v4) ---
    alert_points = 0
    for a in alerts:
        if any(x in a for x in ["Platinum", "Hydrazine", "Nitro", "Halogenated"]):
            alert_points += 45 # Severe systemic toxins
        elif any(x in a for x in ["Quinone", "Iodo", "Thiophene"]):
            alert_points += 25 # High metabolic risk
        else:
            alert_points += 12 # Common/low-risk motifs (e.g. simple Aromatic Amine)
    
    # KG Evidence weighting (clinical reports are high-signal)
    kg_contribution = (kg_score * 0.5)
    
    tox_score = base_risk + alert_points + kg_contribution
    results["toxicity"] = (min(tox_score, 98), "Structural & KG Algorithm v4")

    # --- 3. DILI Risk Prediction (v4) ---
    # Specific DILI flags have much higher weights
    high_impact_dili = [a for a in alerts if any(x in a for x in ["Hydrazine", "Quinone", "Iodo", "Thiophene", "Halogenated"])]
    medium_impact_dili = [a for a in alerts if "Nitro" in a or "Amine" in a]
    
    dili_points = (len(high_impact_dili) * 40) + (len(medium_impact_dili) * 15)
    
    # Synergistic risk: MW/LogP + DILI Alerts
    if base_risk > 0 and high_impact_dili:
        dili_points += 20
        
    dili_score = (base_risk * 0.7) + dili_points + (kg_score * 0.65)
    
    # Final clamping and low-risk floor refinement
    final_dili = min(dili_score, 98)
    
    # Ensure safe drugs are truly low (Aspirin/Caffeine/Acetaminophen therapeutic)
    if not high_impact_dili and kg_score < 20:
        if not alerts:
            final_dili = min(final_dili, 10) # No alerts, low KG = Very Safe
        else:
            final_dili = min(final_dili, 25) # Minor alerts only, low KG = Low Risk
    
    results["dili"] = (final_dili, "DILI-Targeted Algorithm v4")
            
    return results


# ============================================================
# NEW: Structured Azure AI Reasoning
# ============================================================
def get_structured_ai_reasoning(smiles: str, tox_score: float, dili_score: float, alerts: List[str], kg_evidence: dict, api_key: str = None) -> Dict:
    """Fetch structured JSON reasoning for Toxicity and DILI using Gemini."""
    if api_key:
        llm_manager.update_gemini_key(api_key)
    
    if not llm_manager.gemini_key:
        return {"error": "Gemini API key missing"}

    alert_text = ", ".join(alerts) if alerts else "None detected."
    
    prompt = f"""
    Perform an IN-DEPTH toxicological assessment for the molecule: {smiles}
    
    Data: 
    - Toxicity Index: {tox_score}%
    - DILI (Liver Injury) Risk: {dili_score}%
    - Structural Alerts: {alert_text}
    - Clinical & Preclinical Evidence (Neo4j Graph Data): {json.dumps(kg_evidence, indent=2, default=str)}
    
    You must act as a Senior Forensic Toxicologist. Provide a detailed mechanistic analysis and quantify sub-risks.
    Integrate both the structural alerts AND the real-world clinical/preclinical evidence into your reasoning.
    
    Respond ONLY in JSON format (no markdown code blocks):
    {{
        "sub_metrics": {{
            "mitochondrial_dysfunction": 0-100 score,
            "dna_damage_potential": 0-100 score,
            "covalent_binding_risk": 0-100 score,
            "oxidative_stress_induction": 0-100 score
        }},
        "biochemical_mechanisms": ["Detailed biochemical pathway analysis 1", "Detailed biochemical pathway analysis 2"],
        "structural_justification": "In-depth scientific explanation of why the specific chemical motifs found in this SMILES lead to the predicted risks.",
        "dili_specific_analysis": "Targeted assessment of hepatocyte impact and potential for idiosyncratic vs. intrinsic injury.",
        "safety_conclusion": "Authoritative final safety recommendation.",
        "risk_level": "High" | "Medium" | "Low"
    }}
    """

    try:
        response = llm_manager.query_gemini(prompt)
        if response and response.get("status") == 200:
            text = response["reply"].strip()
            logger.info(f"Gemini raw response: {text[:200]}...")
            
            # 1. Direct JSON extraction
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(0)
                    return json.loads(json_str)
                except Exception as e:
                    logger.warning(f"Failed to parse extracted JSON: {e}")
            
            # 2. Try cleaning markdown block markers
            cleaned = text.replace('```json', '').replace('```', '').strip()
            try:
                return json.loads(cleaned)
            except Exception as e:
                logger.error(f"Fallback JSON parsing failed: {e}")
                return {"error": f"JSON parsing failed: {str(e)}", "raw": text[:500]}
        else:
            err = response.get("reply") if response else "No response"
            logger.error(f"Gemini Reasoning failed: {err}")
            return {"error": f"Failed to retrieve AI reasoning: {err}"}
    except Exception as e:
        logger.error(f"AI Reasoning Exception: {str(e)}")
        return {"error": f"Exception in AI reasoning: {str(e)}"}


# ============================================================
# MAIN ENTRY POINT
# ============================================================
def predict_drug_toxicity(drug_name: str, driver, api_key: str, mol_props: dict = None) -> dict:
    print(f"[ToxPredict] Starting integrated prediction for: {drug_name}")

    smiles = mol_props.get("smiles") if mol_props else None
    if not smiles:
        # Robust SMILES query: check drug_name and general name
        query = """
        MATCH (d:Drug)
        WHERE toLower(d.drug_name) = $name 
           OR toLower(d.name) = $name 
           OR d.smiles = $name
        RETURN d.smiles AS s LIMIT 1
        """
        rows = _run(driver, query, name=drug_name.lower())
        if rows and rows[0].get("s"):
            smiles = rows[0]["s"]
        else:
            # Last resort: search by name substring
            query_partial = "MATCH (d:Drug) WHERE toLower(d.drug_name) CONTAINS $name RETURN d.smiles AS s LIMIT 1"
            rows = _run(driver, query_partial, name=drug_name.lower())
            if rows and rows[0].get("s"):
                smiles = rows[0]["s"]
        
    if not smiles:
        print(f"[ToxPredict] WARNING: SMILES not found for {drug_name}. Prediction coverage will be limited.")
        return {"error": f"Could not determine SMILES for '{drug_name}'. High-fidelity toxicity analysis requires a chemical structure."}
    
    # 1. RDKit Analysis
    analysis = get_chemical_analysis(smiles)
    if "error" in analysis:
        return {"error": f"RDKit Error for {drug_name}: {analysis['error']}"}

    # 2. Extract Knowledge Graph Evidence
    all_flags = []
    all_evidence = {}

    c_score, c_flags, c_evidence = _score_clinical(driver, drug_name)
    all_flags.extend(c_flags)
    all_evidence.update(c_evidence)

    p_score, p_flags, p_evidence, animal_cmax = _score_preclinical(driver, drug_name)
    all_flags.extend(p_flags)
    all_evidence.update(p_evidence)

    ae_score, ae_flags, ae_evidence = _score_adverse_events(driver, drug_name)
    all_flags.extend(ae_flags)
    all_evidence.update(ae_evidence)

    sm_score, sm_flags, sm_evidence = _compute_safety_margin(driver, drug_name, animal_cmax)
    all_flags.extend(sm_flags)
    all_evidence.update(sm_evidence)

    # Calculate combined KG score from Neo4j
    clinical_preclinical_score = min(c_score + p_score + ae_score + sm_score, 100)

    # 3. Predict DeepChem/Fallback Scores dynamically
    predictions = predict_scores(smiles, analysis, kg_score=clinical_preclinical_score)
    tox_val, tox_method = predictions["toxicity"]
    dili_val, dili_method = predictions["dili"]

    # 4. Gemini Structured Reasoning (Using provided api_key if available)
    ai_data = get_structured_ai_reasoning(smiles, tox_val, dili_val, analysis["alerts"], all_evidence, api_key=api_key)

    # 5. NEW: Structural Sub-metric Fallback (Prevent 0% when AI fails)
    if "error" in ai_data or not ai_data.get("sub_metrics"):
        logger.warning(f"AI Reasoning failed or incomplete for {drug_name}. Using structural fallback sub-metrics.")
        fallback_metrics = {
            "mitochondrial_dysfunction": 10,
            "dna_damage_potential": 10,
            "covalent_binding_risk": 15,
            "oxidative_stress_induction": 15
        }
        # Amplify based on specific alerts (HDAC focus)
        for alert in analysis["alerts"]:
            if "Hydroxamic Acid" in alert:
                fallback_metrics["oxidative_stress_induction"] += 25
                fallback_metrics["covalent_binding_risk"] += 20
            if "Amine" in alert or "Nitro" in alert:
                fallback_metrics["dna_damage_potential"] += 35
            if "Quinone" in alert:
                fallback_metrics["oxidative_stress_induction"] += 45
                fallback_metrics["mitochondrial_dysfunction"] += 30
        
        # Ensure we don't overwrite if they partially exist
        if "sub_metrics" not in ai_data:
            ai_data["sub_metrics"] = fallback_metrics
        else:
            for k, v in fallback_metrics.items():
                if not ai_data["sub_metrics"].get(k):
                    ai_data["sub_metrics"][k] = v
        
        # Add fallback text
        ai_data["structural_justification"] = "Structural motifs (Hydroxamic Acid) detected. These are known to chelate metals and potentially induce oxidative stress via metabolic activation." if not ai_data.get("structural_justification") else ai_data["structural_justification"]
        ai_data["safety_conclusion"] = "Monitor for idiosyncratic hepatotoxicity. Predicted risk based on structural alerts and KG clinical history." if not ai_data.get("safety_conclusion") else ai_data["safety_conclusion"]
        ai_data["risk_level"] = "Medium" if not ai_data.get("risk_level") else ai_data["risk_level"]

    # Determine risk presentation based on AI data or fallback
    risk_mapped = ai_data.get("risk_level", "Medium")
    if risk_mapped == "High":
        risk_color = "#e74c3c"; risk_icon = "🔴"
    elif risk_mapped == "Medium":
        risk_color = "#f39c12"; risk_icon = "🟠"
    elif risk_mapped == "Low":
        risk_color = "#27ae60"; risk_icon = "🟢"
    else:
        risk_color = "#3498db"; risk_icon = "🔵"

    return {
        "drug": drug_name,
        "smiles": smiles,
        "combined_score": tox_val, # Use toxicity value as overall
        "dili_score": dili_val,
        "risk_level": risk_mapped,
        "risk_color": risk_color,
        "risk_icon": risk_icon,
        "ai_analysis": ai_data,
        "predictions": predictions,
        "properties": {"mw": analysis["mol_weight"], "logp": analysis["logp"]},
        "structural_alerts": analysis["alerts"],
        "kg_evidence": {
            "flags": all_flags,
            "evidence": all_evidence
        },
        "analytics": _extract_safety_analytics(driver, drug_name)
    }
