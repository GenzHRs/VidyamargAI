r"""
Hyperlink Extraction, Categorization & Entity Association Engine for VidyaMarg AI.

Handles hyperlinks as first-class structured data across all resume formats:
- PDF (clickable URI annotations mapped to visible labels via spatial bounding boxes)
- DOCX (Word OpenXML w:hyperlink elements mapped to relationship targets)
- ODT (OpenDocument XML text:a elements mapped to xlink:href)
- HTML (Semantic <a> anchors with href and inner text)
- RTF ({\field{\*\fldinst{HYPERLINK "url"}}{\fldrslt label}})
- Plain text & regex URL/email/phone patterns
"""

import re
import urllib.parse
from typing import Dict, Any, List, Optional, Set, Tuple


# Regex patterns for URL detection
URL_REGEX = re.compile(
    r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")

# Specialized profile URL patterns
LINKEDIN_REGEX = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|pub|profile)/([\w-]+)/?", re.IGNORECASE)
GITHUB_REGEX = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([\w-]+)(?:/[\w.-]+)?/?", re.IGNORECASE)
PORTFOLIO_REGEX = re.compile(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:github\.io|vercel\.app|netlify\.app|dev|me|io|info))/?", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Cleans and standardizes raw URL string."""
    if not url:
        return ""
    clean = str(url).strip()
    # Strip surrounding quotes, brackets, punctuation
    clean = clean.strip(" <>()[]\"'.,;")
    if clean.startswith("mailto:"):
        return clean.lower()
    if clean.startswith("tel:"):
        return clean
    if not clean.startswith(("http://", "https://")) and (clean.startswith("www.") or "." in clean.split("/")[0]):
        clean = "https://" + clean
    if clean.endswith("/") and clean.count("/") >= 3:
        clean = clean.rstrip("/")
    return clean


def validate_url(url: str) -> str:
    """Validates URL structure and returns validation status."""
    if not url:
        return "empty"
    norm = normalize_url(url)
    if norm.startswith(("mailto:", "tel:")):
        return "valid"
    try:
        parsed = urllib.parse.urlparse(norm)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            # Check for suspicious or local schemes
            host = (parsed.hostname or "").lower()
            if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168.") or host.startswith("10."):
                return "untrusted"
            return "valid"
        return "malformed"
    except Exception:
        return "malformed"


def classify_link_type(url: str, label: str = "") -> str:
    """Classifies a URL into a high-level semantic link type."""
    if not url:
        return "other"
    url_lower = url.lower()
    label_lower = (label or "").lower()

    if url_lower.startswith("mailto:") or "@" in url_lower and "http" not in url_lower:
        return "email"
    if url_lower.startswith("tel:"):
        return "phone"

    if "linkedin.com" in url_lower or "linkedin" in label_lower:
        return "linkedin"
    if "github.com" in url_lower or "github" in label_lower:
        if "/" in url_lower.replace("https://github.com/", "").strip("/"):
            return "project_repo"
        return "github"
    if any(k in url_lower for k in ("gitlab.com", "bitbucket.org")):
        return "project_repo"
    if any(k in url_lower for k in ("credly.com", "coursera.org/verify", "udemy.com/certificate", "hackerrank.com/certificates")):
        return "credential"
    if any(k in label_lower for k in ("portfolio", "personal site", "website", "my work")):
        return "portfolio"
    if any(k in url_lower for k in ("vercel.app", "netlify.app", "github.io", "herokuapp.com", "render.com")):
        return "project_demo"
    if any(k in label_lower for k in ("demo", "live", "app", "preview", "link")):
        return "project_demo"
    if any(k in label_lower for k in ("repo", "code", "source")):
        return "project_repo"
    if any(k in url_lower for k in ("twitter.com", "x.com", "medium.com", "dev.to", "kaggle.com", "leetcode.com", "stackoverflow.com")):
        return "social_profile"

    return "other"


def create_hyperlink_record(
    url: str,
    label: str = "",
    source_format: str = "pdf",
    source_page: Optional[int] = 1,
    nearby_text: str = "",
    extraction_method: str = "pdf_uri_annotation",
    associated_entity: Optional[str] = None
) -> Dict[str, Any]:
    """Builds a canonical, validated hyperlink record."""
    norm_url = normalize_url(url)
    clean_label = str(label or "").strip()
    if not clean_label:
        # Use domain or url path as visible fallback
        clean_label = norm_url.replace("https://", "").replace("http://", "").rstrip("/")

    status = validate_url(norm_url)
    link_type = classify_link_type(norm_url, clean_label)

    return {
        "url": norm_url,
        "label": clean_label,
        "link_type": link_type,
        "source_format": source_format,
        "source_page": source_page,
        "nearby_text": nearby_text[:300] if nearby_text else "",
        "extraction_method": extraction_method,
        "validation_status": status,
        "associated_entity": associated_entity
    }


def associate_links_with_resume_entities(
    hyperlinks: List[Dict[str, Any]],
    structured_data: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Associates discovered hyperlinks with the appropriate structured resume entities:
    - Personal info (LinkedIn, GitHub, Portfolio, Email, Custom Links)
    - Projects (repo URLs, demo URLs, project links)
    - Experience (company websites, project references)
    - Certifications (credential verification URLs)
    
    Returns updated (structured_data, enriched_hyperlinks).
    """
    if isinstance(hyperlinks, dict) and isinstance(structured_data, list):
        hyperlinks, structured_data = structured_data, hyperlinks

    if not hyperlinks or not isinstance(structured_data, dict):
        return structured_data, hyperlinks or []

    pi = structured_data.setdefault("personal_info", {})
    existing_custom = pi.setdefault("custom_links", [])
    seen_urls: Set[str] = set()

    for k in ("linkedin_url", "github_url", "portfolio_url", "email"):
        if pi.get(k):
            seen_urls.add(normalize_url(pi[k]))
    for cl in existing_custom:
        if isinstance(cl, dict) and cl.get("url"):
            seen_urls.add(normalize_url(cl["url"]))

    enriched_links: List[Dict[str, Any]] = []

    for link in hyperlinks:
        u = link.get("url")
        if not u:
            continue
        norm_u = normalize_url(u)
        l_type = link.get("link_type") or classify_link_type(norm_u, link.get("label", ""))
        label = link.get("label") or norm_u
        nearby = (link.get("nearby_text") or "").lower()
        associated = None

        # 0. Check if already explicitly associated by layout parser
        if link.get("associated_entity"):
            associated = link["associated_entity"]

        # 1. Personal Profile Links
        if not associated and l_type == "linkedin" and not pi.get("linkedin_url"):
            pi["linkedin_url"] = norm_u
            associated = "personal_info.linkedin_url"
        elif not associated and l_type == "github" and not pi.get("github_url") and norm_u.count("/") <= 4:
            pi["github_url"] = norm_u
            associated = "personal_info.github_url"
        elif not associated and l_type == "portfolio" and not pi.get("portfolio_url"):
            pi["portfolio_url"] = norm_u
            associated = "personal_info.portfolio_url"
        elif not associated and l_type == "email" and not pi.get("email"):
            clean_email = norm_u.replace("mailto:", "")
            pi["email"] = clean_email
            associated = "personal_info.email"
        
        # 2. Project Link Association
        if not associated and l_type in ("project_repo", "project_demo", "other", "github"):
            projs = structured_data.get("projects") or []
            for p in projs:
                p_name = (p.get("name") or p.get("title") or "").strip().lower()
                if not p_name or p_name == "project":
                    continue
                # Match via nearby text, label, or URL slug
                slug_p = re.sub(r"[^\w]+", "-", p_name)
                url_path = norm_u.lower()
                bullets_text = " ".join(p.get("bullets", []) or p.get("responsibilities", [])).lower()
                
                name_match = (p_name in nearby or p_name in label.lower() or nearby in p_name)
                slug_match = (len(slug_p) > 3 and (slug_p in url_path or slug_p.replace("-", "") in url_path))
                bullet_match = (label.lower() in bullets_text if len(label) > 4 else False) or (norm_u.lower() in bullets_text)

                if name_match or slug_match or bullet_match:
                    if not p.get("link"):
                        p["link"] = norm_u
                        p["url"] = norm_u
                        associated = f"projects[{p.get('name')}].link"
                        break

        # 3. Certification Credential Link Association
        if not associated and l_type in ("credential", "other"):
            certs = structured_data.get("certifications") or []
            for c in certs:
                c_name = (c.get("name") or "").strip().lower()
                if c_name and (c_name in nearby or c_name in label.lower() or any(w in norm_u.lower() for w in c_name.split() if len(w) > 4)):
                    if not c.get("credential_url"):
                        c["credential_url"] = norm_u
                        associated = f"certifications[{c.get('name')}].credential_url"
                        break

        # 4. Publication Link Association
        if not associated and any(k in norm_u.lower() for k in ("doi.org", "arxiv.org", "ieeexplore", "acm.org", "springer.com", "researchgate")):
            pubs = structured_data.get("publications") or []
            for pub in pubs:
                pub_title = (pub.get("title") or "").strip().lower()
                if pub_title and (pub_title in nearby or pub_title in label.lower()):
                    if not pub.get("url"):
                        pub["url"] = norm_u
                        associated = f"publications[{pub.get('title')}].url"
                        break

        # 5. Fallback: Add to Custom Links if relevant and unique
        if not associated and norm_u not in seen_urls and l_type not in ("email", "phone"):
            pi["custom_links"].append({"label": label, "url": norm_u})
            seen_urls.add(norm_u)
            associated = "personal_info.custom_links"

        link_copy = dict(link)
        link_copy["associated_entity"] = associated
        enriched_links.append(link_copy)

    structured_data["hyperlinks"] = enriched_links
    return structured_data, enriched_links
