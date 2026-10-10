"""
Canonical Project Normalizer & Bullet Deduplication Service for VidyaMarg AI.

Provides authoritative, idempotent normalization of resume project records:
1. Strips bullet marker noise and deduplicates project bullet points (case/punctuation-insensitive).
2. Prevents paragraph-to-bullet duplication (clears redundant overview descriptions while preserving distinct context).
3. Normalizes and tokenizes technology lists without dropping valid skills.
4. Produces a consistent, canonical project schema for LaTeX and ReportLab renderers.
"""

import re
import string
from typing import Any, Dict, List, Optional, Set


KNOWN_TECH_TERMS = [
    "FastAPI", "Python", "PostgreSQL", "Azure OCR", "Azure", "OCR", "NER", "Gemini LLM", "Gemini", "LLM",
    "React", "Next.js", "Vue.js", "Vue", "Angular", "Node.js", "Express", "Django", "Flask", "Spring Boot",
    "PyTorch", "TensorFlow", "Keras", "Scikit-Learn", "Pandas", "NumPy", "Docker", "Kubernetes", "K8s",
    "MongoDB", "Redis", "SQLite", "MySQL", "Oracle", "AWS", "GCP", "OpenAI", "LangChain", "LlamaIndex",
    "Qdrant", "ChromaDB", "Java", "C++", "C#", "Rust", "Go", "Golang", "TypeScript", "JavaScript",
    "HTML", "CSS", "Tailwind", "Git", "GitHub", "CI/CD", "Linux", "Bash", "REST API", "REST", "GraphQL",
    "gRPC", "Kafka", "RabbitMQ", "Spark", "Hadoop", "Airflow", "MLOps", "NLP", "LLMs", "RAG", "Computer Vision",
    "Kotlin", "Android", "AccessibilityService", "NVIDIA API", "NVIDIA"
]


def clean_bullet_text(text: str) -> str:
    """
    Cleans leading bullet glyphs, numbering patterns, and excessive whitespace.
    Preserves all internal wording, punctuation, and capitalization.
    """
    if not text:
        return ""
    s = str(text).strip()
    # Strip bullet glyphs, dashes, asterisks
    s = re.sub(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*", "", s).strip()
    # Strip numeric prefixes like "1.", "1)", "(1)", "[1]"
    s = re.sub(r"^(?:\(?\d+[.)\]]|\b[a-zA-Z][.)\]])\s*", "", s).strip()
    # Collapse multiple internal spaces
    s = re.sub(r"[ \t]+", " ", s)
    return s


def _comparison_key(text: str) -> str:
    """
    Produces a normalized comparison key for bullet matching.
    Case-insensitive, whitespace-collapsed, punctuation-stripped.
    """
    cleaned = clean_bullet_text(text).lower()
    # Strip common sentence-ending and separating punctuation
    key = re.sub(r"[^\w\s]", "", cleaned)
    key = re.sub(r"\s+", " ", key).strip()
    return key


def normalize_technologies_list(tech_input: Any) -> List[str]:
    """
    Parses, tokenizes, and cleans technology strings and lists.
    Handles concatenated tech stacks (e.g., 'FastAPIPythonPostgreSQLAzure OCRNERGemini LLM')
    as well as delimiter-separated strings (comma, semicolon, pipe, bullet, slash).
    """
    if not tech_input:
        return []

    raw_items: List[str] = []
    if isinstance(tech_input, str):
        if re.search(r"[,;|•·/\n]", tech_input):
            raw_items = [t.strip() for t in re.split(r"[,;|•·/\n]\s*", tech_input) if t.strip()]
        else:
            raw_items = [tech_input.strip()]
    elif isinstance(tech_input, list):
        for item in tech_input:
            if isinstance(item, str) and item.strip():
                if re.search(r"[,;|•·/\n]", item):
                    raw_items.extend([t.strip() for t in re.split(r"[,;|•·/\n]\s*", item) if t.strip()])
                else:
                    raw_items.append(item.strip())
            elif item:
                raw_items.append(str(item).strip())
    else:
        raw_items = [str(tech_input).strip()]

    final_techs: List[str] = []
    seen: Set[str] = set()

    for item in raw_items:
        if not item:
            continue
        # Attempt to detect concatenated known terms
        sorted_terms = sorted(KNOWN_TECH_TERMS, key=len, reverse=True)
        found_matches: List[Tuple_Match] = []

        for term in sorted_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for m in pattern.finditer(item):
                start, end = m.span()
                overlap = any(not (end <= s or start >= e) for s, e, _ in found_matches)
                if not overlap:
                    found_matches.append((start, end, term))

        if len(found_matches) > 1:
            found_matches.sort(key=lambda x: x[0])
            for _, _, term in found_matches:
                t_lower = term.lower()
                if t_lower not in seen:
                    seen.add(t_lower)
                    final_techs.append(term)
        else:
            clean_item = clean_bullet_text(item)
            if clean_item and clean_item.lower() not in seen:
                seen.add(clean_item.lower())
                final_techs.append(clean_item)

    return final_techs


Tuple_Match = Any  # helper type alias


def _is_description_redundant(clean_desc: str, bullets: List[str]) -> bool:
    """
    Determines if overview description is composed entirely of the bullet points.
    Returns True if redundant (should be cleared), False if it contains genuinely unique context.
    """
    if not clean_desc or not bullets:
        return False

    desc_key = _comparison_key(clean_desc)
    joined_bullets_key = _comparison_key(" ".join(bullets))

    # Exact match with joined bullets
    if desc_key == joined_bullets_key:
        return True

    # Check if single bullet is identical to description
    if any(desc_key == _comparison_key(b) for b in bullets):
        return True

    # Sentence-by-sentence check
    sentences = [s.strip() for s in re.split(r"[.!?]\s*", clean_desc) if s.strip()]
    if not sentences:
        return False

    all_sentences_in_bullets = True
    bullet_keys = [_comparison_key(b) for b in bullets]

    for sent in sentences:
        sent_key = _comparison_key(sent)
        if not sent_key:
            continue
        # Check if this sentence appears in or matches any bullet
        matched = any(sent_key in bk or bk in sent_key for bk in bullet_keys)
        if not matched:
            all_sentences_in_bullets = False
            break

    return all_sentences_in_bullets


def canonicalize_project(proj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a single project dictionary into the canonical format:
    - Exactly ONE title / name.
    - Normalized date range.
    - Deduplicated canonical bullet array (order preserved, first occurrence kept).
    - Redundant description cleared; genuinely distinct description preserved.
    - Normalized technologies list and formatted tech_stack string.
    - Explicitly sets features = [] to prevent legacy concatenation bugs.
    - Idempotent: Repeated application does not mutate canonical data.
    """
    if not isinstance(proj, dict):
        return {}

    name = str(proj.get("name") or proj.get("title") or proj.get("project_name") or "Project").strip()
    start_date = str(proj.get("start_date") or "").strip()
    end_date = str(proj.get("end_date") or proj.get("duration") or "").strip()
    dates = str(proj.get("dates") or f"{start_date} {end_date}".strip()).strip()

    # 1. Collect all bullet point candidates
    # Priority order: bullets, then responsibilities, then features, then achievements
    raw_bullet_candidates: List[Any] = []

    for field in ("bullets", "responsibilities", "features", "achievements"):
        val = proj.get(field)
        if isinstance(val, list):
            raw_bullet_candidates.extend(val)
        elif isinstance(val, str) and val.strip():
            # If string contains multiple lines, split them
            lines = [l.strip() for l in re.split(r"[\r\n]+", val) if l.strip()]
            raw_bullet_candidates.extend(lines)

    # 2. Deduplicate bullets preserving original order and capitalization
    canonical_bullets: List[str] = []
    seen_bullet_keys: Set[str] = set()

    for item in raw_bullet_candidates:
        if not item:
            continue
        if isinstance(item, str):
            # Check if item itself contains newline-separated bullets
            sub_items = [s.strip() for s in re.split(r"[\r\n]+", item) if s.strip()]
        else:
            sub_items = [str(item).strip()]

        for sub in sub_items:
            clean_b = clean_bullet_text(sub)
            if not clean_b:
                continue
            key = _comparison_key(clean_b)
            if key and key not in seen_bullet_keys:
                seen_bullet_keys.add(key)
                canonical_bullets.append(clean_b)

    # Merge accidental wrapped lines caused by newline splits within a single bullet sentence
    merged_bullets: List[str] = []
    for b in canonical_bullets:
        b_clean = b.strip()
        if not b_clean:
            continue
        if merged_bullets and not merged_bullets[-1].endswith(('.', '!', '?', ':')) and b_clean[0].islower():
            if merged_bullets[-1].endswith("-"):
                merged_bullets[-1] = merged_bullets[-1][:-1] + b_clean
            else:
                merged_bullets[-1] = merged_bullets[-1] + " " + b_clean
        else:
            merged_bullets.append(b_clean)

    # Re-deduplicate merged bullets to guarantee unique canonical list
    final_canonical_bullets: List[str] = []
    final_seen_keys: Set[str] = set()
    for b in merged_bullets:
        key = _comparison_key(b)
        if key and key not in final_seen_keys:
            final_seen_keys.add(key)
            final_canonical_bullets.append(b)

    canonical_bullets = final_canonical_bullets

    # 3. Handle technologies
    raw_tech = proj.get("technologies") or proj.get("tech_stack") or []
    norm_tech = normalize_technologies_list(raw_tech)
    tech_str = ", ".join(norm_tech) if norm_tech else (proj.get("tech_stack") if isinstance(proj.get("tech_stack"), str) else "")

    # 4. Description handling & deduplication against bullets
    raw_desc = str(proj.get("description") or "").strip()
    clean_desc = clean_bullet_text(raw_desc) if raw_desc else ""

    if clean_desc:
        if not canonical_bullets:
            # If there were no bullets, treat description as bullet or retain description
            if "\n" in clean_desc or clean_desc.startswith(("-", "*", "•")):
                extracted_bullets = [clean_bullet_text(l) for l in re.split(r"[\r\n]+", clean_desc) if clean_bullet_text(l)]
                canonical_bullets = extracted_bullets
                final_description = ""
            else:
                final_description = clean_desc
        else:
            if _is_description_redundant(clean_desc, canonical_bullets):
                final_description = ""
            else:
                final_description = clean_desc
    else:
        final_description = ""

    link = str(proj.get("link") or proj.get("url") or proj.get("project_url") or "").strip()

    return {
        "name": name,
        "title": name,
        "start_date": start_date,
        "end_date": end_date,
        "dates": dates,
        "description": final_description or None,
        "bullets": canonical_bullets or ["Designed and implemented project functionality."],
        "responsibilities": canonical_bullets or ["Designed and implemented project functionality."],
        "features": [],  # explicitly cleared so legacy concatenation never re-duplicates
        "technologies": norm_tech,
        "tech_stack": tech_str,
        "link": link,
        "url": link
    }


def canonicalize_projects_list(projects: Any) -> List[Dict[str, Any]]:
    """
    Normalizes a list of projects.
    Never merges separate projects.
    Every project in the list is independently canonicalized.
    """
    if not projects:
        return []

    if isinstance(projects, dict):
        return [canonicalize_project(projects)]

    if not isinstance(projects, list):
        return []

    result = []
    for p in projects:
        if isinstance(p, dict):
            result.append(canonicalize_project(p))
    return result
