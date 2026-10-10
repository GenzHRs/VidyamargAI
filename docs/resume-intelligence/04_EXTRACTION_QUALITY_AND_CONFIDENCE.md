# Extraction Quality, Confidence Scoring & Consistency Auditing

**Document Version**: 2.0.0  
**Status**: Production Verified  
**Engine Reference**: `backend/app/services/resume_extractor_engine.py`

---

## 1. Quality Assurance Philosophy

VidyaMarg AI operates under strict **zero-hallucination guarantees**:
1. The parser must never fabricate credentials, degrees, employers, or dates not present in the candidate's original document.
2. The parser must never collapse multiple employers or omit intermediate career steps.
3. The parser must detect missing or ambiguous data and communicate it explicitly to the candidate via structured warnings and actionable remediation steps.

---

## 2. Confidence Scoring Algorithm

Every extraction computes a deterministic **Confidence Score** ($\text{Score} \in [0.20, 1.00]$):

$$\text{Confidence} = 1.00 - \sum \text{Penalties}$$

### Penalty Weights

| Quality Criterion | Condition Trigger | Penalty | Rationale |
| :--- | :--- | :--- | :--- |
| **Missing Full Name** | Candidate name missing or generic ("Candidate", "null") | `-0.25` | Fundamental identity missing from header. |
| **Missing Contact Email** | No valid RFC 5322 email extracted | `-0.15` | Critical communication channel missing. |
| **Missing Phone Number** | No valid 7-15 digit phone string found | `-0.10` | Secondary contact missing. |
| **Zero Categorized Skills** | No skills detected in any category | `-0.20` | Skills section absent or unparseable. |
| **Missing Career History** | Neither work experience nor education entries extracted | `-0.25` | Core professional qualification history missing. |
| **Lower Bound Clamp** | Final score below minimum | Floor at `0.20` | Guarantees non-zero floor for valid uploads. |

---

## 3. Consistency Checks & Completeness Auditing

The `_normalize_and_validate_extraction` engine runs post-extraction integrity checks:

### 3.1 Project Completeness Audit
- Evaluates raw text for marker patterns indicating project counts:
  - `tech_lines = re.findall(r"(?:tech\s*stack|technologies|tools)\s*[:\-]", raw_text)`
  - `numbered_projects = re.findall(r"^\s*\d+[\.\)]\s*[A-Z]", raw_text)`
- If detected project indicators exceed extracted projects ($E_{\text{expected}} > E_{\text{extracted}}$), an explicit warning is attached:
  ```text
  "Extraction Completeness Alert: Document contains evidence of at least 4 project blocks, but 2 were extracted."
  ```

### 3.2 Chronological Date Anomaly Audit
- Evaluates extracted start and end dates for each work experience block.
- If $\text{Year}_{\text{start}} > \text{Year}_{\text{end}}$ and the role is not marked as current, an anomaly warning is logged:
  ```text
  "Work Experience entry #2 (TechCorp): Start date (2022) is after end date (2020)."
  ```

### 3.3 Employer vs. Job Designation Audit
- Deterministically audits extracted entries to ensure `employer` and `designation` are not reversed:
  - Checks against `COMPANY_KEYWORDS` (`inc`, `corp`, `ltd`, `technologies`, `solutions`, `labs`, `llc`, etc.)
  - Checks against `DESIGNATION_KEYWORDS` (`engineer`, `developer`, `architect`, `lead`, `manager`, `analyst`, etc.)
  - If `employer` contains designation terms and `designation` contains company terms, they are swapped to canonical orientation automatically.

---

## 4. Multi-Pass Safety Merge (AI + Heuristic Fallback)

When AI extraction executes, the engine simultaneously runs the 2-pass deterministic heuristic parser:
1. If the heuristic parser recovers more distinct projects than the AI model ($N_{\text{heuristic}} > N_{\text{AI}}$), the missing projects are merged into the final output.
2. If the heuristic parser discovers additional previous employers that the AI model collapsed, those experience entries are merged.

This dual-layer architecture guarantees that no project or employment history is ever lost due to model truncation or context limitations.
