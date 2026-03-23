import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()
from services.neo4j_service import get_driver

# ============================================================
# SCHEMA TEXT — reflects actual Neo4j property names
# ============================================================
SCHEMA_TEXT = """
Node labels and ACTUAL property names (verified from live Neo4j database):

- Drug: drug_name, iupac_name, smiles, molecular_weight, logp, cid, h_donor, h_acceptor
- ClinicalData [HAS_CLINICAL_DATA]: CONTAINER node (has 'name') - subnodes below hold actual data
  Sub-nodes linked from ClinicalData:
    - DosingAdministration: dose_level, route, schedule, cycle_length, infusion_duration
    - PopulationCharacteristics: sample_size, median_age, age_range, male_percent, female_percent, disease_subtype, disease_indication
    - StudyMetadata: sponsor, study_ids, study_phase, study_design, status
    - StudyOverview: name (title)
    - TreatmentManagement: supportive_care, anc_nadir_threshold, platelet_nadir_threshold, dose_reductions
    - EligibilityCriteria: bilirubin, platelet, alt_ast, creatinine_clearance, anc
- Pharmacokinetics [via HAS_CLINICAL_DATA->...]: cmax, auc, half_life, clearance, metabolism, protein_binding_percent
- EfficacyOutcomes: orr_percent, cr_rate_percent, pr_rate_percent, median_time_to_response, median_duration_of_response
- AdverseEvents [HAS_ADVERSE_EVENTS]: name (container)
- AdverseEvent [HAS_EVENT]: name, counts (list), percents (list), grade34_counts, grade34_percents, sae (boolean), teae (boolean)
- SafetyData: total_aes, death_count, hepatotoxicity_warning, qtc_change
- PreclinicalToxicology [HAS_PRECLINICAL_TOXICOLOGY]: summary, species, target_organs
- PreclinicalStudy [HAS_PRECLINICAL_STUDY]: cmax, auc, noael, loael, dose, route, species, strain, sex, alt, ast, t_half, tmax, primary_histopath, adverse_events
- ToxicokineticParameters: name, study, species
- ToxicokineticMeasurement (Schema A - Rat): dose_mg_per_kg, sex, dose_group,
    cmax_day1_ug_per_mL, cmax_day5_ug_per_mL, cmax_day151_ug_per_mL,
    auc_day1_ug_h_per_mL, auc_day5_ug_h_per_mL, auc_day151_ug_h_per_mL
- ToxicokineticMeasurement (Schema B - Dog): dose_mg_kg_day, sex,
    cmax_ug_ml_day1, cmax_ug_ml_day5, cmax_ug_ml_day151,
    auc_0_24h_ug_h_ml_day1, auc_0_24h_ug_h_ml_day5, auc_0_24h_ug_h_ml_day151
- ExposureMeasurement: cmax_ug_per_mL, auc_ug_h_per_mL, dose_mg_per_kg, species, sex, day
- ExperimentalGroup: dose_mg_per_kg_per_day, group_number, terminal_m, terminal_f, tk_m, tk_f
- MicroscopicFinding: name, male_10, male_25, male_50, male_100, female_10, female_25, female_50, female_100, phase
- ClinicalChemistry: name, unit, parameter
- ClinicalChemistryCycle: parameter, cycle, dose10_m, dose10_f, dose25_m, dose25_f, dose100_m, dose100_f
- TranscriptomicData [HAS_TRANSCRIPTOMIC_DATA]: name
- Signature [HAS_SIGNATURE]: signature_id, cell_line, concentration, tissue, time, gene_targets
- DifferentialExpression [HAS_DIFFERENTIAL_EXPRESSION]: gene_symbol, gene_id, logFC, p_value
- ReproductiveToxicity: warnings, developmental_warnings
- Carcinogenicity: studies_conducted
- Genotoxicity: conclusion
- MechanismOfAction: description, cellular_effects, molecular_targets
- RecommendedDose: dose, unit, route, administration_days, cycle_length, infusion_duration, frequency
- SpecialPopulations: pregnancy, hepatic_impairment, pediatric
- Contraindications: list, rationale
- DrugInteractions: clinical_significance, cyp_interactions, interacting_drugs

Key Paths:
(:Drug)-[:HAS_CLINICAL_DATA]->(:ClinicalData)-[*1..2]->(clinical_subnodes)
(:Drug)-[*1..3]->(:Pharmacokinetics) — has cmax, auc, half_life
(:Drug)-[:HAS_ADVERSE_EVENTS]->(:AdverseEvents)-[:HAS_EVENT]->(:AdverseEvent) — name, counts, percents, sae
(:Drug)-[*1..3]->(:PreclinicalStudy) — cmax, auc, noael, loael, species
(:Drug)-[*1..5]->(:ToxicokineticMeasurement) — use BOTH property schemas
(:Drug)-[*1..5]->(:ExposureMeasurement) — cmax_ug_per_mL, auc_ug_h_per_mL
(:Drug)-[:SIMILAR_TO]-(:Drug)
"""

# ============================================================
# CYPHER TEMPLATES — using actual property names
# ============================================================
CYPHER_TEMPLATES = {
    "sad_mad_cohorts": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[:HAS_CLINICAL_DATA]->(cd:ClinicalData)-[*1..2]->(pk:Pharmacokinetics)
OPTIONAL MATCH (cd)-[*1..2]->(da:DosingAdministration)
OPTIONAL MATCH (cd)-[*1..2]->(sm:StudyMetadata)
RETURN d.drug_name AS drug, da.dose_level AS dose, pk.cmax AS cmax, pk.auc AS auc, 
       sm.study_phase AS phase, sm.study_design AS design, sm.study_ids AS study_id
ORDER BY da.dose_level DESC
""",
    "fih_exposures": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(da:DosingAdministration)
OPTIONAL MATCH (d)-[*1..3]->(em:ExposureMeasurement)
RETURN d.drug_name AS drug, da.dose_level AS dose, em.cmax_ug_per_mL AS projected_cmax, 
       em.auc_ug_h_per_mL AS projected_auc, em.species AS species
""",
    "ae_soc_gi": """
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
{DRUG_FILTER}
WHERE toLower(ae.name) CONTAINS 'gastro' OR toLower(ae.name) CONTAINS 'nausea' 
   OR toLower(ae.name) CONTAINS 'vomiting' OR toLower(ae.name) CONTAINS 'diarrhea'
RETURN d.drug_name AS drug, ae.name AS event, ae.counts AS counts, ae.percents AS percents,
       ae.grade34_counts AS grade34_counts, ae.grade34_percents AS grade34_percents
ORDER BY ae.name
""",
    "ae_hepatobiliary": """
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
{DRUG_FILTER}
WHERE toLower(ae.name) CONTAINS 'hepato' OR toLower(ae.name) CONTAINS 'liver' 
   OR toLower(ae.name) CONTAINS 'transaminase' OR toLower(ae.name) CONTAINS 'bilirubin'
   OR toLower(ae.name) CONTAINS 'ast' OR toLower(ae.name) CONTAINS 'alt'
RETURN d.drug_name AS drug, ae.name AS event, ae.counts AS counts, ae.percents AS percents
""",
    "pd_efficacy": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(eo:EfficacyOutcomes)
OPTIONAL MATCH (d)-[*1..3]->(moa:MechanismOfAction)
RETURN d.drug_name AS drug, eo.orr_percent AS orr, eo.cr_rate_percent AS cr, 
       moa.cellular_effects AS effects, moa.molecular_targets AS targets
""",
    "pharmacokinetics": """
MATCH (d:Drug)-[*1..3]->(pk:Pharmacokinetics)
{DRUG_FILTER}
RETURN d.drug_name AS drug, pk.cmax AS cmax, pk.auc AS auc, pk.half_life AS half_life, pk.clearance AS clearance, pk.metabolism AS metabolism, pk.protein_binding_percent AS protein_binding_pct
ORDER BY d.drug_name
""",
    "cmax_clinical": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(pk:Pharmacokinetics)
OPTIONAL MATCH (d)-[*1..2]->(da:DosingAdministration)
RETURN d.drug_name AS drug, pk.cmax AS cmax, pk.auc AS auc, pk.half_life AS half_life, pk.clearance AS clearance, da.dose_level AS dose_level, da.route AS route, da.schedule AS schedule
ORDER BY d.drug_name
""",
    "cmax_preclinical_tk": """
MATCH (d:Drug)-[*1..5]->(tm:ToxicokineticMeasurement)
{DRUG_FILTER}
RETURN d.drug_name AS drug, tm.sex AS sex, tm.dose_mg_per_kg AS dose_rat, tm.dose_mg_kg_day AS dose_dog,
    tm.cmax_day1_ug_per_mL AS cmax_day1_rat, tm.cmax_day5_ug_per_mL AS cmax_day5_rat, tm.cmax_day151_ug_per_mL AS cmax_day151_rat,
    tm.cmax_ug_ml_day1 AS cmax_day1_dog, tm.cmax_ug_ml_day5 AS cmax_day5_dog, tm.cmax_ug_ml_day151 AS cmax_day151_dog,
    tm.auc_day1_ug_h_per_mL AS auc_day1_rat, tm.auc_day5_ug_h_per_mL AS auc_day5_rat,
    tm.auc_0_24h_ug_h_ml_day1 AS auc_day1_dog, tm.auc_0_24h_ug_h_ml_day5 AS auc_day5_dog
ORDER BY d.drug_name
LIMIT 50
""",
    "cmax_preclinical_exposure": """
MATCH (d:Drug)-[*1..5]->(em:ExposureMeasurement)
{DRUG_FILTER}
RETURN d.drug_name AS drug, em.species AS species, em.sex AS sex, em.dose_mg_per_kg AS dose_mg_per_kg,
    em.cmax_ug_per_mL AS cmax_ug_per_mL, em.auc_ug_h_per_mL AS auc_ug_h_per_mL, em.day AS day
ORDER BY d.drug_name, em.dose_mg_per_kg
LIMIT 50
""",
    "auc_clinical": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(pk:Pharmacokinetics)
OPTIONAL MATCH (d)-[*1..2]->(da:DosingAdministration)
RETURN d.drug_name AS drug, pk.auc AS auc, pk.cmax AS cmax, pk.half_life AS half_life, pk.clearance AS clearance, da.dose_level AS dose_level
ORDER BY d.drug_name
""",
    "adverse_events": """
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
{DRUG_FILTER}
RETURN d.drug_name AS drug, ae.name AS event, ae.counts AS counts, ae.percents AS percents,
    ae.grade34_counts AS grade34_counts, ae.grade34_percents AS grade34_percents,
    ae.sae AS is_sae, ae.teae AS is_teae
ORDER BY ae.name
""",
    "sae": """
MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
WHERE ae.sae = true OR toLower(toString(ae.sae)) = 'true'
{DRUG_FILTER_AND}
RETURN d.drug_name AS drug, ae.name AS event, ae.counts AS counts, ae.percents AS percents
ORDER BY d.drug_name
""",
    "noael": """
MATCH (d:Drug)-[*1..3]->(ps:PreclinicalStudy)
{DRUG_FILTER}
RETURN d.drug_name AS drug, ps.species AS species, ps.sex AS sex, ps.noael AS noael, ps.loael AS loael,
    ps.dose AS dose, ps.route AS route, ps.cmax AS cmax, ps.auc AS auc, ps.alt AS alt, ps.ast AS ast
ORDER BY d.drug_name
LIMIT 30
""",
    "safety": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..2]->(sd:SafetyData)
OPTIONAL MATCH (d)-[*1..3]->(rt:ReproductiveToxicity)
OPTIONAL MATCH (d)-[*1..3]->(geo:Genotoxicity)
RETURN d.drug_name AS drug, sd.hepatotoxicity_warning AS hep_warning, sd.total_aes AS total_aes,
    sd.death_count AS death_count, sd.qtc_change AS qtc, rt.warnings AS repro_warning, geo.conclusion AS geno
ORDER BY d.drug_name
""",
    "ast_alt": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(clchem:ClinicalChemistry)
OPTIONAL MATCH (d)-[*1..4]->(cycle:ClinicalChemistryCycle)
OPTIONAL MATCH (d)-[*1..3]->(ps:PreclinicalStudy)
RETURN d.drug_name AS drug, clchem.parameter AS clinical_parameter, cycle.parameter AS cycle_param, cycle.cycle AS cycle_name,
    cycle.dose10_m AS dose10_m, cycle.dose10_f AS dose10_f, cycle.dose25_m AS dose25_m, cycle.dose25_f AS dose25_f,
    cycle.dose100_m AS dose100_m, cycle.dose100_f AS dose100_f,
    ps.species AS species, ps.alt AS alt_preclinical, ps.ast AS ast_preclinical
ORDER BY d.drug_name
LIMIT 30
""",
    "platelet": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..2]->(tm:TreatmentManagement)
OPTIONAL MATCH (d)-[*1..2]->(ec:EligibilityCriteria)
OPTIONAL MATCH (d)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
WHERE toLower(ae.name) CONTAINS 'thrombocytopenia' OR toLower(ae.name) CONTAINS 'platelet'
RETURN d.drug_name AS drug, tm.platelet_nadir_threshold AS platelet_threshold, tm.dose_reductions AS dose_reductions,
    ec.platelet AS platelet_eligibility, ae.name AS ae_name, ae.percents AS ae_percents
ORDER BY d.drug_name
""",
    "efficacy": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(eo:EfficacyOutcomes)
OPTIONAL MATCH (d)-[*1..3]->(se:SubgroupEfficacy)
OPTIONAL MATCH (d)-[*1..2]->(pop:PopulationCharacteristics)
RETURN d.drug_name AS drug, eo.orr_percent AS orr, eo.cr_rate_percent AS cr_rate, eo.pr_rate_percent AS pr_rate,
    eo.median_time_to_response AS time_to_response, eo.median_duration_of_response AS dur_response,
    se.aitl_percent AS aitl_orr, se.ptcl_nos_percent AS ptcl_nos_orr,
    pop.sample_size AS n, pop.disease_indication AS indication
ORDER BY d.drug_name
""",
    "study_design": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..2]->(sm:StudyMetadata)
OPTIONAL MATCH (d)-[*1..2]->(da:DosingAdministration)
OPTIONAL MATCH (d)-[*1..2]->(pop:PopulationCharacteristics)
OPTIONAL MATCH (d)-[*1..2]->(rd:RecommendedDose)
RETURN d.drug_name AS drug, sm.sponsor AS sponsor, sm.study_ids AS study_ids, sm.study_phase AS phase,
    sm.study_design AS design, sm.status AS status, da.dose_level AS dose, da.route AS route,
    da.schedule AS schedule, da.cycle_length AS cycle, pop.sample_size AS n,
    rd.dose AS recommended_dose, rd.unit AS dose_unit
ORDER BY d.drug_name
""",
    "mechanism": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..2]->(moa:MechanismOfAction)
RETURN d.drug_name AS drug, moa.description AS mechanism, moa.molecular_targets AS targets, moa.cellular_effects AS effects
ORDER BY d.drug_name
""",
    "transcriptomics": """
MATCH (d:Drug)-[:HAS_TRANSCRIPTOMIC_DATA]->(td:TranscriptomicData)-[:HAS_SIGNATURE]->(sig:Signature)
{DRUG_FILTER}
RETURN d.drug_name AS drug, td.name AS dataset, sig.cell_line AS cell_line, sig.concentration AS concentration,
    sig.tissue AS tissue, sig.time AS time, sig.gene_targets AS gene_targets
ORDER BY d.drug_name LIMIT 20
""",
    "preclinical_all": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(ps:PreclinicalStudy)
OPTIONAL MATCH (d)-[*1..5]->(em:ExposureMeasurement)
OPTIONAL MATCH (d)-[*1..3]->(pt:PreclinicalToxicology)
RETURN d.drug_name AS drug, ps.species AS study_species, ps.noael AS noael, ps.cmax AS preclinical_cmax,
    ps.auc AS preclinical_auc, ps.alt AS alt, ps.ast AS ast, ps.primary_histopath AS histopath,
    em.species AS exposure_species, em.cmax_ug_per_mL AS cmax_exposure, em.dose_mg_per_kg AS dose_exp,
    em.day AS day, em.sex AS sex, pt.target_organs AS target_organs, pt.summary AS summary
ORDER BY d.drug_name LIMIT 50
""",
    "recommended_dose": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..3]->(rd:RecommendedDose)
OPTIONAL MATCH (d)-[*1..2]->(da:DosingAdministration)
RETURN d.drug_name AS drug, rd.dose AS rec_dose, rd.unit AS unit, rd.route AS route,
    rd.administration_days AS days, rd.cycle_length AS cycle, rd.frequency AS frequency,
    da.dose_level AS dose_levels, da.infusion_duration AS infusion_duration
ORDER BY d.drug_name
""",
    "drug_interactions": """
MATCH (d:Drug)
{DRUG_FILTER}
OPTIONAL MATCH (d)-[*1..2]->(di:DrugInteractions)
RETURN d.drug_name AS drug, di.interacting_drugs AS interactions, di.cyp_interactions AS cyp, di.clinical_significance AS significance
ORDER BY d.drug_name
""",
}


def _match_template(question: str):
    q = question.lower()
    if any(w in q for w in ["sad", "mad", "highest cohort", "highest sad", "highest mad"]):
        return "sad_mad_cohorts"
    if any(w in q for w in ["fih", "projected", "human exposure at different doses"]):
        return "fih_exposures"
    if any(w in q for w in ["gi soc", "gastrointestinal"]):
        return "ae_soc_gi"
    if any(w in q for w in ["hepatobiliary", "transaminase", "bilirubin", "liver elevation", "ast elevation", "alt elevation"]):
        return "ae_hepatobiliary"
    if any(w in q for w in ["pd measure", "efficacy measure", "pd and ae", "correlation between ae frequency"]):
        return "pd_efficacy"
    if any(w in q for w in ["sae", "serious adverse", "serious ae"]):
        return "sae"
    if any(w in q for w in ["transcriptomic", "transcriptomics", "signature", "lincs", "gene expression"]):
        return "transcriptomics"
    if any(w in q for w in ["adverse event", "adverse events", " ae ", "side effect", "what ae"]):
        return "adverse_events"
    if any(w in q for w in ["noael", "loael", "no observed", "no-observed", "safety margin"]):
        return "noael"
    if any(w in q for w in ["platelet", "thrombocytopenia", "anc", "neutrophil"]):
        return "platelet"
    if any(w in q for w in ["hepatotox", "dili", "liver warning", "qtc", "qt prolongation"]):
        return "safety"
    if any(w in q for w in ["safety"]):
        return "safety"
    if any(w in q for w in ["ast", "alt", "alanine", "aspartate", "liver enzyme", "clinical chemistry"]):
        return "ast_alt"
    if any(w in q for w in ["orr", "response rate", "efficacy", "overall response", "cr rate", "pr rate"]):
        return "efficacy"
    if any(w in q for w in ["mechanism", "moa", "hdac", "target", "how does"]):
        return "mechanism"
    if any(w in q for w in ["interaction", "drug interaction", "cyp", "concomitant"]):
        return "drug_interactions"
    if any(w in q for w in ["study design", "study metadata", "sponsor", "study id", "enrolled"]):
        return "study_design"
    if any(w in q for w in ["recommended dose", "approved dose", "label dose", "prescribing"]):
        return "recommended_dose"
    if any(w in q for w in ["cmax", "c_max", "peak concentration", "maximum concentration"]):
        if any(w in q for w in ["preclinical", "animal", "rat", "dog", "mouse", "tox", "toxico"]):
            return "cmax_preclinical_tk"
        return "cmax_clinical"
    if any(w in q for w in ["auc", "area under curve", "area under the curve"]):
        if any(w in q for w in ["preclinical", "animal"]):
            return "cmax_preclinical_tk"
        return "auc_clinical"
    if any(w in q for w in ["pk", "pharmacokinetic", "half life", "clearance", "t1/2"]):
        return "pharmacokinetics"
    if any(w in q for w in ["preclinical", "animal study", "in vivo", "rat study", "dog study", "toxicology"]):
        return "preclinical_all"
    return None


def _build_drug_filter(drug_name, template_key):
    if not drug_name:
        return ""
    if template_key == "sae":
        return f"AND toLower(d.drug_name) = toLower('{drug_name}')"
    else:
        return f"WHERE toLower(d.drug_name) = toLower('{drug_name}')"


# ============================================================
# DEEP CONTEXT EXTRACTOR
# ============================================================
def _extract_full_drug_context(drug_name: str) -> dict:
    context = {"drug": drug_name, "found": False, "categories": {}}
    driver = get_driver()
    if not driver:
        return context

    queries = {
        "drug_info": f"MATCH (d:Drug) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(d) AS props LIMIT 1",
        "pharmacokinetics": f"MATCH (d:Drug)-[*1..3]->(pk:Pharmacokinetics) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(pk) AS props LIMIT 5",
        "dosing_admin": f"MATCH (d:Drug)-[*1..2]->(da:DosingAdministration) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(da) AS props LIMIT 5",
        "recommended_dose": f"MATCH (d:Drug)-[*1..3]->(rd:RecommendedDose) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(rd) AS props LIMIT 5",
        "study_metadata": f"MATCH (d:Drug)-[*1..2]->(sm:StudyMetadata) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(sm) AS props LIMIT 5",
        "population": f"MATCH (d:Drug)-[*1..2]->(pop:PopulationCharacteristics) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(pop) AS props LIMIT 5",
        "efficacy": f"MATCH (d:Drug)-[*1..3]->(eo:EfficacyOutcomes) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(eo) AS props LIMIT 5",
        "safety_data": f"MATCH (d:Drug)-[*1..2]->(sd:SafetyData) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(sd) AS props LIMIT 5",
        "adverse_events": f"""
            MATCH (d:Drug)-[:HAS_ADVERSE_EVENTS]->(ae_c)-[:HAS_EVENT]->(ae:AdverseEvent)
            WHERE toLower(d.drug_name) = toLower('{drug_name}')
            RETURN properties(ae) AS props ORDER BY ae.name LIMIT 50
        """,
        "treatment_management": f"MATCH (d:Drug)-[*1..2]->(tm:TreatmentManagement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(tm) AS props LIMIT 5",
        "eligibility": f"MATCH (d:Drug)-[*1..2]->(ec:EligibilityCriteria) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(ec) AS props LIMIT 5",
        "preclinical_studies": f"MATCH (d:Drug)-[*1..3]->(ps:PreclinicalStudy) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(ps) AS props LIMIT 20",
        "preclinical_toxicology": f"MATCH (d:Drug)-[*1..2]->(pt:PreclinicalToxicology) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(pt) AS props LIMIT 5",
        "exposure_measurements": f"MATCH (d:Drug)-[*1..5]->(em:ExposureMeasurement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(em) AS props LIMIT 30",
        "toxicokinetic_measurements": f"MATCH (d:Drug)-[*1..5]->(tm:ToxicokineticMeasurement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(tm) AS props LIMIT 30",
        "toxicity_measurements": f"MATCH (d:Drug)-[*1..5]->(tm:ToxicityMeasurement) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(tm) AS props LIMIT 20",
        "microscopic_findings": f"""
            MATCH (d:Drug)-[*1..5]->(mf)
            WHERE toLower(d.drug_name) = toLower('{drug_name}')
              AND labels(mf)[0] IN ['MicroscopicFinding','MicroscopicFindings']
            RETURN labels(mf)[0] AS label, properties(mf) AS props LIMIT 30
        """,
        "clinical_chemistry": f"""
            MATCH (d:Drug)-[*1..4]->(cc)
            WHERE toLower(d.drug_name) = toLower('{drug_name}')
              AND labels(cc)[0] IN ['ClinicalChemistry','ClinicalChemistryCycle']
            RETURN labels(cc)[0] AS label, properties(cc) AS props LIMIT 20
        """,
        "mechanism_of_action": f"MATCH (d:Drug)-[*1..2]->(moa:MechanismOfAction) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(moa) AS props LIMIT 3",
        "subgroup_efficacy": f"MATCH (d:Drug)-[*1..3]->(se:SubgroupEfficacy) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(se) AS props LIMIT 5",
        "transcriptomic_data": f"MATCH (d:Drug)-[:HAS_TRANSCRIPTOMIC_DATA]->(td:TranscriptomicData) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(td) AS props LIMIT 10",
        "signatures": f"MATCH (d:Drug)-[:HAS_TRANSCRIPTOMIC_DATA]->(:TranscriptomicData)-[:HAS_SIGNATURE]->(sig:Signature) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(sig) AS props LIMIT 20",
        "top_diff_expression": f"""
            MATCH (d:Drug)-[*1..4]->(de:DifferentialExpression)
            WHERE toLower(d.drug_name) = toLower('{drug_name}')
            RETURN properties(de) AS props
            ORDER BY toFloat(de.logFC) DESC LIMIT 15
        """,
        "reproductive_tox": f"MATCH (d:Drug)-[*1..3]->(rt:ReproductiveToxicity) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(rt) AS props LIMIT 3",
        "genotoxicity": f"MATCH (d:Drug)-[*1..3]->(geo:Genotoxicity) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(geo) AS props LIMIT 3",
        "special_populations": f"MATCH (d:Drug)-[*1..3]->(sp:SpecialPopulations) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(sp) AS props LIMIT 3",
        "contraindications": f"MATCH (d:Drug)-[*1..3]->(ci:Contraindications) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(ci) AS props LIMIT 3",
        "drug_interactions": f"MATCH (d:Drug)-[*1..3]->(di:DrugInteractions) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN properties(di) AS props LIMIT 3",
        "similar_molecules": f"MATCH (d:Drug)-[:SIMILAR_TO]-(sim:Drug) WHERE toLower(d.drug_name) = toLower('{drug_name}') RETURN sim.drug_name AS name, properties(sim) AS props LIMIT 10",
    }

    with driver.session() as session:
        for category, query in queries.items():
            try:
                results = list(session.run(query))
                if results:
                    context["found"] = True
                    context["categories"][category] = [dict(r) for r in results]
            except Exception as e:
                print(f"[WARN] context query '{category}' failed: {e}")

    return context


def _serialize_context(context: dict) -> str:
    lines = [f"=== KNOWLEDGE GRAPH DATA for {context['drug']} ===\n"]
    for category, records in context.get("categories", {}).items():
        if not records:
            continue
        lines.append(f"\n--- {category.replace('_',' ').title()} ({len(records)} records) ---")
        for rec in records[:30]:
            props = rec.get("props", rec)
            if isinstance(props, dict):
                clean = {k: v for k, v in props.items()
                         if v is not None and k != 'measurements_html' and str(v).strip()}
                if clean:
                    lines.append("  " + json.dumps(clean, default=str))
            else:
                lines.append("  " + json.dumps(rec, default=str)[:400])
    return "\n".join(lines)


# ============================================================
# GEMINI API — with retry, backoff, multi-model rotation
# ============================================================
import time

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.5-flash",
]


def _call_gemini(prompt: str, api_key: str, max_retries: int = 2) -> str:
    """Call Gemini with exponential backoff and multi-model rotation."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 3000}
    }
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        for attempt in range(max_retries):
            try:
                r = requests.post(url, json=payload, timeout=35)
                if r.status_code == 200:
                    data = r.json()
                    cands = data.get("candidates", [])
                    if cands and cands[0].get("content", {}).get("parts"):
                        return cands[0]["content"]["parts"][0]["text"]
                elif r.status_code == 429:
                    # Rate limited — wait then try next attempt or next model
                    wait = 2 ** attempt
                    print(f"[WARN] {model} rate limited, waiting {wait}s...")
                    time.sleep(wait)
                elif r.status_code == 503:
                    time.sleep(1)
                else:
                    print(f"[WARN] {model} HTTP {r.status_code}: {r.text[:200]}")
                    break  # Non-retryable error, try next model
            except Exception as e:
                print(f"[WARN] {model} attempt {attempt+1} exception: {e}")
                time.sleep(1)
    print("[ERROR] All Gemini models exhausted")
    return None


# ============================================================
# LOCAL RULE-BASED FORMATTER — answers without LLM
# ============================================================
def _format_results_locally(question: str, results: list, context: dict, drug_name: str) -> str:
    """
    Build a structured markdown answer directly from graph data.
    No LLM needed — used as fallback when API is rate-limited.
    """
    q = question.lower()
    cats = context.get("categories", {}) if context else {}
    lines = [f"📊 **Based on Knowledge Graph data for {drug_name or 'all drugs'}:**\n"]

    # --- Pharmacokinetics / Cmax / AUC ---
    if any(w in q for w in ["cmax", "auc", "pk", "pharmacokinetic", "half life", "clearance", "sad", "fih"]):
        pk_records = cats.get("pharmacokinetics", [])
        if pk_records:
            lines.append("### 💊 Clinical Pharmacokinetics")
            lines.append("| Parameter | Value |")
            lines.append("|-----------|-------|")
            for rec in pk_records:
                p = rec.get("props", rec)
                for k, v in p.items():
                    if v:
                        lines.append(f"| {k.replace('_',' ').title()} | {v} |")

        dosing = cats.get("dosing_admin", [])
        if dosing:
            lines.append("\n### 💉 Dosing Administration")
            for rec in dosing:
                p = rec.get("props", rec)
                for k, v in p.items():
                    if v:
                        lines.append(f"- **{k.replace('_',' ').title()}**: {v}")

        tk = cats.get("toxicokinetic_measurements", [])
        if tk:
            lines.append("\n### 🐀 Preclinical Toxicokinetic Measurements")
            lines.append("| Dose (mg/kg) | Sex | Cmax Day1 | Cmax Day5 | Cmax Day151 | AUC Day1 | AUC Day5 |")
            lines.append("|---|---|---|---|---|---|---|")
            for rec in tk[:20]:
                p = rec.get("props", rec)
                dose = p.get("dose_mg_per_kg") or p.get("dose_mg_kg_day") or "-"
                sex = p.get("sex", "-")
                c1 = p.get("cmax_day1_ug_per_mL") or p.get("cmax_ug_ml_day1") or "-"
                c5 = p.get("cmax_day5_ug_per_mL") or p.get("cmax_ug_ml_day5") or "-"
                c151 = p.get("cmax_day151_ug_per_mL") or p.get("cmax_ug_ml_day151") or "-"
                a1 = p.get("auc_day1_ug_h_per_mL") or p.get("auc_0_24h_ug_h_ml_day1") or "-"
                a5 = p.get("auc_day5_ug_h_per_mL") or p.get("auc_0_24h_ug_h_ml_day5") or "-"
                lines.append(f"| {dose} | {sex} | {c1} μg/mL | {c5} μg/mL | {c151} μg/mL | {a1} | {a5} |")

        em = cats.get("exposure_measurements", [])
        if em:
            lines.append("\n### 🔬 Exposure Measurements")
            lines.append("| Species | Sex | Dose (mg/kg) | Day | Cmax (μg/mL) | AUC |")
            lines.append("|---|---|---|---|---|---|")
            for rec in em[:20]:
                p = rec.get("props", rec)
                lines.append(f"| {p.get('species','-')} | {p.get('sex','-')} | {p.get('dose_mg_per_kg','-')} | {p.get('day','-')} | {p.get('cmax_ug_per_mL','-')} | {p.get('auc_ug_h_per_mL','-')} |")

    # --- Adverse Events ---
    if any(w in q for w in ["adverse", " ae ", "side effect", "sae", "serious", "event"]):
        ae_records = cats.get("adverse_events", [])
        safety = cats.get("safety_data", [])
        if ae_records:
            lines.append("\n### ⚠️ Adverse Events")
            # SAEs first
            saes = [r for r in ae_records if str(r.get("props", r).get("sae", "")).lower() == "true"]
            teaes = [r for r in ae_records if str(r.get("props", r).get("sae", "")).lower() != "true"]
            if "sae" in q or "serious" in q:
                display = saes if saes else ae_records
                lines.append("**Serious Adverse Events (SAEs):**")
            else:
                display = teaes if teaes else ae_records
            lines.append("| # | Event | Count | % | SAE |")
            lines.append("|---|-------|-------|---|-----|")
            for i, rec in enumerate(display[:20], 1):
                p = rec.get("props", rec)
                name = p.get("name", "?")
                counts = p.get("counts", "-")
                percents = p.get("percents", "-")
                is_sae = "✓" if str(p.get("sae", "")).lower() == "true" else ""
                lines.append(f"| {i} | {name} | {counts} | {percents} | {is_sae} |")
        if safety:
            p = safety[0].get("props", safety[0])
            lines.append(f"\n**Total AEs:** {p.get('total_aes', '-')}  |  **Deaths:** {p.get('death_count', '-')}  |  **QTc:** {p.get('qtc_change', '-')}")
            if p.get('hepatotoxicity_warning'):
                lines.append(f"\n⚠️ **Hepatotoxicity:** {p.get('hepatotoxicity_warning')}")

    # --- Preclinical / NOAEL ---
    if any(w in q for w in ["noael", "loael", "preclinical", "animal", "rat", "dog", "safety margin"]):
        ps_records = cats.get("preclinical_studies", [])
        if ps_records:
            lines.append("\n### 🐾 Preclinical Studies")
            lines.append("| Species | Sex | NOAEL (mg/kg) | LOAEL | Cmax | AUC | ALT | AST | Route |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for rec in ps_records:
                p = rec.get("props", rec)
                lines.append(f"| {p.get('species','-')} | {p.get('sex','-')} | {p.get('noael','-')} | {p.get('loael','-')} | {p.get('cmax','-')} | {p.get('auc','-')} | {p.get('alt','-')} | {p.get('ast','-')} | {p.get('route','-')} |")

    # --- Efficacy ---
    if any(w in q for w in ["orr", "response rate", "efficacy", "cr rate", "pr rate", "clinical benefit"]):
        eo = cats.get("efficacy", [])
        if eo:
            lines.append("\n### 📈 Efficacy Outcomes")
            p = eo[0].get("props", eo[0])
            lines.append(f"- **ORR**: {p.get('orr_percent', '-')}%")
            lines.append(f"- **CR Rate**: {p.get('cr_rate_percent', '-')}%")
            lines.append(f"- **PR Rate**: {p.get('pr_rate_percent', '-')}%")
            lines.append(f"- **Time to Response**: {p.get('median_time_to_response', '-')}")
            lines.append(f"- **Duration of Response**: {p.get('median_duration_of_response', '-')}")
        se = cats.get("subgroup_efficacy", [])
        if se:
            p = se[0].get("props", se[0])
            lines.append(f"- **AITL subgroup ORR**: {p.get('aitl_percent', '-')}%")
            lines.append(f"- **PTCL-NOS subgroup ORR**: {p.get('ptcl_nos_percent', '-')}%")

    # --- Safety / Hepatotoxicity ---
    if any(w in q for w in ["safety", "hepatotox", "dili", "liver", "ast", "alt", "alanine", "aspartate"]):
        cc = cats.get("clinical_chemistry", [])
        if cc:
            lines.append("\n### 🧪 Clinical Chemistry")
            for rec in cc[:10]:
                p = rec.get("props", rec)
                if p.get("cycle"):
                    lines.append(f"- **{p.get('parameter','')} ({p.get('cycle','')})**: 10mg M={p.get('dose10_m','-')} F={p.get('dose10_f','-')}, 25mg M={p.get('dose25_m','-')} F={p.get('dose25_f','-')}, 100mg M={p.get('dose100_m','-')} F={p.get('dose100_f','-')}")

    # --- Mechanism ---
    if any(w in q for w in ["mechanism", "moa", "hdac", "how does", "target"]):
        moa = cats.get("mechanism_of_action", [])
        if moa:
            p = moa[0].get("props", moa[0])
            lines.append("\n### 🔬 Mechanism of Action")
            lines.append(f"**Description**: {p.get('description', '-')}")
            lines.append(f"**Molecular Targets**: {p.get('molecular_targets', '-')}")
            lines.append(f"**Cellular Effects**: {p.get('cellular_effects', '-')}")

    # --- Recommended Dose ---
    if any(w in q for w in ["recommended dose", "approved dose", "label dose", "fda dose"]):
        rd = cats.get("recommended_dose", [])
        if rd:
            p = rd[0].get("props", rd[0])
            lines.append("\n### 💊 Recommended Dose")
            lines.append(f"- **Dose**: {p.get('dose', '-')} {p.get('unit', '')}")
            lines.append(f"- **Route**: {p.get('route', '-')}")
            lines.append(f"- **Schedule**: {p.get('administration_days', '-')} / {p.get('cycle_length', '-')}")

    # --- Study Design ---
    if any(w in q for w in ["study design", "sponsor", "study id", "enrolled", "sample size", "phase"]):
        sm = cats.get("study_metadata", [])
        pop = cats.get("population", [])
        if sm:
            p = sm[0].get("props", sm[0])
            lines.append("\n### 📋 Study Design")
            lines.append(f"- **Sponsor**: {p.get('sponsor', '-')}")
            lines.append(f"- **Phase**: {p.get('study_phase', '-')}")
            lines.append(f"- **Study IDs**: {p.get('study_ids', '-')}")
            lines.append(f"- **Design**: {p.get('study_design', '-')}")
            lines.append(f"- **Status**: {p.get('status', '-')}")
        if pop:
            p = pop[0].get("props", pop[0])
            lines.append(f"- **N**: {p.get('sample_size', '-')}")
            lines.append(f"- **Median Age**: {p.get('median_age', '-')} (range {p.get('age_range', '-')})")
            lines.append(f"- **Indication**: {p.get('disease_indication', '-')} — {p.get('disease_subtype', '-')}")

    # If nothing specific matched, show summary of all available data
    if len(lines) <= 2:
        lines.append("\n### 📁 Available Data Summary")
        for cat, records in cats.items():
            if records:
                lines.append(f"- **{cat.replace('_',' ').title()}**: {len(records)} record(s) available")
        lines.append("\n*Ask a more specific question to extract detailed values.*")

    return "\n".join(lines)


def _generate_cypher_via_gemini(question: str, drug_name: str, api_key: str) -> str:
    drug_ctx = (
        f"Filter ONLY to drug '{drug_name}' using: WHERE toLower(d.drug_name) = toLower('{drug_name}')"
        if drug_name
        else "Do NOT filter — query ALL drugs."
    )
    prompt = f"""You are a Neo4j Cypher expert. Write ONLY valid Cypher (no markdown fences).

Schema:
{SCHEMA_TEXT}

Drug context: {drug_ctx}
Question: {question}

Key rules:
- Use variable-length paths [*1..5] for deep nodes
- For clinical Cmax/AUC: use Pharmacokinetics node (has cmax, auc, half_life, clearance)
- For preclinical Cmax: use ExposureMeasurement (cmax_ug_per_mL) or ToxicokineticMeasurement
- For adverse events: use AdverseEvent node (has name, counts, percents, sae=true/false)
- Use OPTIONAL MATCH for nodes that may not exist
- Always RETURN actual property values
- LIMIT 50
"""
    return _call_gemini(prompt, api_key)


def _run_cypher(cypher: str):
    driver = get_driver()
    if not driver:
        return []
    try:
        with driver.session() as session:
            result = session.run(cypher)
            rows = []
            for record in result:
                if hasattr(record, 'keys'):
                    rows.append(dict(record))
                elif isinstance(record, dict):
                    rows.append(record)
                else:
                    rows.append(str(record))
            return rows
    except Exception as e:
        print(f"[ERROR] Cypher failed: {e}")
        return None


# ============================================================
# MAIN ENTRY POINT
# ============================================================
def get_chatbot_response(user_query: str, drug_name: str = None) -> dict:
    from services.llm_service import llm_manager
    api_key = llm_manager.gemini_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"reply": "No Gemini API key configured.", "status": 401}
    driver = get_driver()
    if not driver:
        return {"reply": "Graph database not connected.", "status": 500}

    try:
        cypher = None
        results = None

        # STEP 1: Template query
        template_key = _match_template(user_query)
        if template_key:
            print(f"[INFO] Template: {template_key}")
            drug_filter = _build_drug_filter(drug_name, template_key)
            tmpl = CYPHER_TEMPLATES.get(template_key)
            if tmpl:
                if template_key == "sae":
                    cypher = tmpl.replace("{DRUG_FILTER_AND}", drug_filter)
                else:
                    cypher = tmpl.replace("{DRUG_FILTER}", drug_filter)
                cypher = cypher.strip()
                results = _run_cypher(cypher)

            # Fallback for Cmax: try preclinical if clinical empty
            if not results and template_key == "cmax_clinical":
                for alt in ["cmax_preclinical_tk", "cmax_preclinical_exposure"]:
                    alt_filter = _build_drug_filter(drug_name, alt)
                    c2 = CYPHER_TEMPLATES[alt].replace("{DRUG_FILTER}", alt_filter).strip()
                    r2 = _run_cypher(c2)
                    if r2:
                        results = r2
                        cypher = c2
                        break

        # STEP 2: Gemini-generated Cypher if no template matched or template gave nothing
        if not results and (template_key is None or results is None):
            print("[INFO] Gemini Cypher generation fallback")
            gen_cypher = _generate_cypher_via_gemini(user_query, drug_name, api_key)
            if gen_cypher:
                gen_cypher = re.sub(r"^```(?:cypher)?\n?", "", gen_cypher.strip(), flags=re.IGNORECASE)
                gen_cypher = re.sub(r"\n?```$", "", gen_cypher.strip()).strip()
                cypher = gen_cypher
                results = _run_cypher(cypher)

        # Filter out all-null result rows (sometimes templates return [{key: null}])
        if results:
            results = [r for r in results if any(v is not None for v in r.values())]

        # STEP 3: ALWAYS extract full deep context from graph (runs independently of API)
        context = {}
        context_text = None
        if drug_name:
            print(f"[INFO] Extracting full graph context for {drug_name}...")
            context = _extract_full_drug_context(drug_name)
            if context.get("found"):
                context_text = _serialize_context(context)
                print(f"[INFO] Context: {len(context_text)} chars, {len(context.get('categories', {}))} categories")

        # STEP 4: Synthesize answer — try Gemini first, fall back to local formatter
        answer = None

        if results or context_text:
            results_str = json.dumps(results[:60], indent=2, default=str) if results else "No structured query results."
            context_block = context_text[:5500] if context_text else "No additional context."

            prompt = f"""You are an expert clinical pharmacologist and drug safety analyst.
Your goal is to provide a HIGHLY PRECISE and DIRECT answer to the user's question using the provided Knowledge Graph data.

Question: {user_query}
Drug focus: {drug_name or 'all drugs'}

=== STRUCTURED QUERY RESULTS ({len(results) if results else 0} rows) ===
{results_str}

=== FULL KNOWLEDGE GRAPH CONTEXT ===
{context_block}

CRITICAL INSTRUCTIONS:
1. **Direct Answer First**: Start your response with a clear, concise sentence that directly answers the specific question (e.g., "The highest SAD cohort Cmax for Belinostat was X at dose Y.").
2. **Intelligence**: If the user asks for "highest", "lowest", "total", or "rank", you MUST analyze the data provided above to perform that comparison or calculation yourself.
3. **Evidence**: Following the direct answer, provide a concise summary or a small markdown table of the supporting evidence from the graph data.
4. **No Data Dumps**: Do not dump all categories. Only show data relevant to the question.
5. **Transparency**: If multiple different values exist (e.g., across studies or species), mention them briefly to be accurate.
6. **No "No Data"**: If the answer is in the data, find it. Do not say "data not available" if a value exists in the context block.
7. **Prefix**: Start with "📊 Based on Knowledge Graph data:"
"""
            answer = _call_gemini(prompt, api_key)

            # If Gemini is rate-limited/unavailable, use local formatter
            if not answer:
                print("[INFO] Gemini unavailable — using local rule-based formatter")
                answer = _format_results_locally(user_query, results or [], context, drug_name)

        # Absolute last resort: Gemini general knowledge
        if not answer:
            print("[INFO] No graph data + no Gemini — trying general knowledge")
            answer = _call_gemini(
                f"""You are a pharmaceutical expert. Answer about {drug_name or 'the drug'}.
Prefix with "📚 Based on general biomedical knowledge:".
Question: {user_query}""",
                api_key
            )

        # Final fallback: local general summary from any context found
        if not answer and context.get("found"):
            answer = _format_results_locally(user_query, [], context, drug_name)

        if not answer:
            answer = f"⚠️ No data found in the knowledge graph for **{drug_name}** related to this question. The database may not contain this information, or the API is temporarily unavailable. Please try again in a moment."

        return {
            "reply": answer,
            "status": 200,
            "cypher": cypher,
            "result_count": len(results) if results else 0,
            "context_used": bool(context_text)
        }

    except Exception as e:
        print(f"[ERROR] get_chatbot_response: {e}")
        import traceback
        traceback.print_exc()
        return {"reply": f"Unexpected error: {e}", "status": 500}
