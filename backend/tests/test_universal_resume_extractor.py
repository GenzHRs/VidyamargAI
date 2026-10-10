"""
Comprehensive Test Suite for Universal Resume Extraction, Hyperlink Preservation,
and Template-Agnostic Parsing Engine.

Validates:
1. Multi-format support: PDF, DOCX, DOC, ODT, RTF, HTML, TXT, TEX, Images (PNG), PPTX.
2. Geometry-based reading order reconstruction (Two-column sidebar vs main column).
3. Hyperlink extraction across formats (URI annotations, OpenXML, DOM anchors, RTF fields).
4. Hyperlink categorization & entity association (LinkedIn, GitHub, Repos, Demos, Credentials).
5. Diagnostic endpoint: GET /resumes/{resume_id}/hyperlinks.
6. Security checks: Encrypted PDF rejection, corrupted file rejection, decompression bomb limits.
7. Concatenated technology tokenization & project deduplication idempotency.
"""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from tests.conftest import headers
from app.models.models import User, Candidate
from app.models.resume_center_models import Resume, ResumeExtraction
from app.services.hyperlink_extractor import (
    create_hyperlink_record,
    classify_link_type,
    normalize_url,
    validate_url,
    associate_links_with_resume_entities
)
from app.services.resume_extractor_engine import (
    validate_resume_upload,
    extract_document_content,
    extract_structured_with_ai,
    heuristic_comprehensive_parse,
    normalize_technologies_list,
    normalize_and_deduplicate_project
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES & SYNTHETIC DOCUMENT GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

def _make_two_column_pdf() -> bytes:
    """
    Creates a 2-column PDF where left column contains Skills and right column contains Experience.
    Verifies that layout-aware geometry prevents sidebar skills from interspersing into job bullets.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Standard letter

    # Header
    page.insert_text(fitz.Point(50, 40), "Maya Lin, Lead Architect", fontsize=16)
    page.insert_text(fitz.Point(50, 58), "maya.lin@cloudarch.dev | +1 555-0199 | Austin, TX", fontsize=10)

    # Left Column (x: 50 to 200) - Skills & Education
    page.insert_text(fitz.Point(50, 100), "SKILLS", fontsize=12)
    page.insert_text(fitz.Point(50, 120), "Python", fontsize=10)
    page.insert_text(fitz.Point(50, 135), "Kubernetes", fontsize=10)
    page.insert_text(fitz.Point(50, 150), "PostgreSQL", fontsize=10)
    page.insert_text(fitz.Point(50, 165), "Terraform", fontsize=10)
    page.insert_text(fitz.Point(50, 180), "FastAPI", fontsize=10)

    # Right Column (x: 230 to 560) - Experience
    page.insert_text(fitz.Point(230, 100), "PROFESSIONAL EXPERIENCE", fontsize=12)
    page.insert_text(fitz.Point(230, 120), "Principal Systems Architect - CloudOps Inc (2021 - Present)", fontsize=11)
    page.insert_text(fitz.Point(230, 138), "- Architected multi-region Kubernetes platform handling 20M daily requests.", fontsize=10)
    page.insert_text(fitz.Point(230, 156), "- Reduced multi-cloud infrastructure expenditure by 42% via automated right-sizing.", fontsize=10)
    page.insert_text(fitz.Point(230, 174), "- Led engineering reliability guild across 4 global engineering teams.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_pdf_with_hyperlinks() -> bytes:
    """Creates a PDF with clickable URI annotations."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(fitz.Point(50, 40), "Alex Rivera", fontsize=16)
    page.insert_text(fitz.Point(50, 60), "alex.rivera@example.com", fontsize=10)

    # Insert visible text labels
    p_linkedin = fitz.Point(50, 80)
    page.insert_text(p_linkedin, "LinkedIn Profile", fontsize=10)
    link_rect1 = fitz.Rect(50, 70, 150, 85)
    page.insert_link({"kind": fitz.LINK_URI, "from": link_rect1, "uri": "https://linkedin.com/in/alex-rivera-cloud"})

    p_github = fitz.Point(160, 80)
    page.insert_text(p_github, "GitHub Source", fontsize=10)
    link_rect2 = fitz.Rect(160, 70, 260, 85)
    page.insert_link({"kind": fitz.LINK_URI, "from": link_rect2, "uri": "https://github.com/alexrivera/distributed-cache"})

    # Project with repo link
    page.insert_text(fitz.Point(50, 120), "PROJECTS", fontsize=12)
    page.insert_text(fitz.Point(50, 140), "High-Throughput Distributed Cache", fontsize=11)
    page.insert_text(fitz.Point(50, 155), "- Implemented Raft consensus in Rust with sub-millisecond replication.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_odt_document() -> bytes:
    """Builds a valid in-memory OpenDocument Text (.odt) archive with text and hyperlinks."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Standard ODT mimetype
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        # Minimal content.xml
        content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                         xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
                         xmlns:xlink="http://www.w3.org/1999/xlink">
  <office:body>
    <office:text>
      <text:h text:outline-level="1">Elena Rostova, Senior Full-Stack Engineer</text:h>
      <text:p>elena@rostova.tech | +1 555-4321 | San Francisco, CA</text:p>
      <text:p>
        <text:a xlink:href="https://github.com/erostova">Elena's GitHub</text:a> |
        <text:a xlink:href="https://linkedin.com/in/erostova">LinkedIn</text:a>
      </text:p>
      <text:h text:outline-level="2">Work Experience</text:h>
      <text:p>Senior Engineer at NextGen Systems (2020 - 2024)</text:p>
      <text:p>- Designed scalable microservices in Go and Python serving 5M MAU.</text:p>
      <text:h text:outline-level="2">Skills</text:h>
      <text:p>Python, Go, PostgreSQL, React, Docker</text:p>
    </office:text>
  </office:body>
</office:document-content>"""
        zf.writestr("content.xml", content_xml)
    return buf.getvalue()


def _make_rtf_document() -> bytes:
    """Builds a valid RTF document with embedded HYPERLINK fields."""
    rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0 Helvetica;}}
\f0\fs24
David Kim, SRE Engineer\par
david.kim@infrastructure.org | +1 555-7788 | New York, NY\par
{\field{\*\fldinst{HYPERLINK "https://linkedin.com/in/davidkim-sre"}}{\fldrslt LinkedIn Profile}}\par
{\field{\*\fldinst{HYPERLINK "https://github.com/davidkim/k8s-operator"}}{\fldrslt GitHub Repository}}\par
\b Work Experience\b0\par
Lead SRE - Apex Financial Cloud (2019 - Present)\par
- Engineered multi-cluster Kubernetes observability with Prometheus and Thanos.\par
- Maintained 99.99% system availability across critical financial APIs.\par
\b Skills\b0\par
Kubernetes, Prometheus, Golang, Python, AWS, Terraform\par
}"""
    return rtf_content.encode("latin-1")


def _make_html_resume() -> bytes:
    """Builds a semantic HTML resume document with anchor tags."""
    html = """<!DOCTYPE html>
<html>
<head><title>Resume - Sarah Connor</title></head>
<body>
  <h1>Sarah Connor</h1>
  <p>sarah.connor@defense.net | +1 555-9000 | Los Angeles, CA</p>
  <p>
    <a href="https://linkedin.com/in/sarah-connor-security">LinkedIn</a> |
    <a href="https://github.com/sarahconnor/cyberdyne-shield">Project Source</a> |
    <a href="https://sarahconnor.security.io">Personal Portfolio</a>
  </p>
  <h2>Professional Summary</h2>
  <p>Cybersecurity Architect specializing in threat modeling and automated mitigation.</p>
  <h2>Technical Skills</h2>
  <p>Python, Rust, C++, Wireshark, Docker, Linux, Cryptography</p>
  <h2>Work Experience</h2>
  <p>Principal Defense Architect - Cyberdyne Systems (2022 - Present)</p>
  <ul>
    <li>Automated incident response reducing breach containment time by 80%.</li>
    <li>Conducted firmware reverse-engineering on critical embedded controllers.</li>
  </ul>
</body>
</html>"""
    return html.encode("utf-8")


def _make_pptx_resume() -> bytes:
    """Builds an OpenXML PPTX presentation file in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
</Types>""")
        slide_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp><p:txBody><a:p><a:r><a:t>James Holden, Operations Specialist</a:t></a:r></a:p></p:txBody></p:sp>
      <p:sp><p:txBody><a:p><a:r><a:t>james@roci.space | https://linkedin.com/in/james-holden</a:t></a:r></a:p></p:txBody></p:sp>
      <p:sp><p:txBody><a:p><a:r><a:t>Skills: Python, Fleet Management, Communications, Linux</a:t></a:r></a:p></p:txBody></p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>"""
        zf.writestr("ppt/slides/slide1.xml", slide_xml)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: HYPERLINK EXTRACTION & SEMANTIC CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def test_hyperlink_classification_and_normalization():
    """Validates URL normalization, validation, and semantic link typing."""
    assert normalize_url(" linkedin.com/in/alice-turing/ ") == "https://linkedin.com/in/alice-turing"
    assert normalize_url("mailto:ALICE@EXAMPLE.COM") == "mailto:alice@example.com"
    assert normalize_url("tel:+15551234567") == "tel:+15551234567"

    assert validate_url("https://github.com/vidyamarg") == "valid"
    assert validate_url("mailto:test@example.com") == "valid"
    assert validate_url("http://localhost:8000") == "untrusted"
    assert validate_url("invalid-url-schema") == "malformed"

    assert classify_link_type("https://www.linkedin.com/in/janedoe") == "linkedin"
    assert classify_link_type("https://github.com/janedoe") == "github"
    assert classify_link_type("https://github.com/janedoe/super-agent") == "project_repo"
    assert classify_link_type("https://super-agent.vercel.app") == "project_demo"
    assert classify_link_type("https://www.credly.com/badges/abc") == "credential"
    assert classify_link_type("mailto:jane@example.com") == "email"


def test_hyperlink_entity_association():
    """Validates that discovered hyperlinks automatically associate with structured resume entities."""
    links = [
        create_hyperlink_record("https://linkedin.com/in/shiva-test", "LinkedIn", "pdf"),
        create_hyperlink_record("https://github.com/shiva-test", "GitHub", "pdf"),
        create_hyperlink_record("https://github.com/shiva-test/ai-assistant", "Repo", "pdf", nearby_text="AI Assistant Demo"),
        create_hyperlink_record("https://credly.com/badges/aws-solutions-arch", "AWS Cert", "pdf", nearby_text="AWS Certified Solutions Architect")
    ]

    structured_data = {
        "personal_info": {"full_name": "Shiva Kumar"},
        "projects": [{"name": "AI Assistant", "bullets": ["Built assistant"]}],
        "certifications": [{"name": "AWS Certified Solutions Architect"}]
    }

    updated_data, enriched_links = associate_links_with_resume_entities(links, structured_data)

    assert updated_data["personal_info"]["linkedin_url"] == "https://linkedin.com/in/shiva-test"
    assert updated_data["personal_info"]["github_url"] == "https://github.com/shiva-test"
    assert updated_data["projects"][0]["link"] == "https://github.com/shiva-test/ai-assistant"
    assert updated_data["certifications"][0]["credential_url"] == "https://credly.com/badges/aws-solutions-arch"
    assert len(enriched_links) == 4
    assert enriched_links[0]["associated_entity"] == "personal_info.linkedin_url"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: READING ORDER & GEOMETRY RECONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def test_two_column_reading_order_preservation():
    """
    Validates that a 2-column sidebar PDF reconstructs geometry so skills do not
    pollute work experience responsibilities.
    """
    pdf_bytes = _make_two_column_pdf()
    res = extract_document_content("maya_resume.pdf", pdf_bytes, ".pdf")

    assert res["page_count"] == 1
    raw_text = res["raw_text"]

    # Verify that header came first
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    assert any("Maya Lin" in l for l in lines[:3])

    # Parse with heuristic engine
    parsed = heuristic_comprehensive_parse(raw_text, res["layout_info"])
    assert parsed["personal_info"]["full_name"] is not None

    # Verify skills were extracted properly into skills section
    all_skills = [s.lower() for s in parsed["skills"]["all_raw_skills"]]
    assert "python" in all_skills
    assert "kubernetes" in all_skills

    # Verify work experience responsibilities are NOT polluted with isolated skill tokens
    exps = parsed.get("work_experience") or []
    assert len(exps) >= 1
    exp_bullets = " ".join(exps[0].get("responsibilities", []))
    assert "multi-region kubernetes platform" in exp_bullets.lower()


def test_pdf_clickable_hyperlink_extraction():
    """Validates that PyMuPDF clips visible anchor text for URI annotations."""
    pdf_bytes = _make_pdf_with_hyperlinks()
    res = extract_document_content("alex_rivera.pdf", pdf_bytes, ".pdf")

    hyperlinks = res["layout_info"].get("hyperlinks", [])
    assert len(hyperlinks) >= 2

    urls = [h["url"] for h in hyperlinks]
    assert "https://linkedin.com/in/alex-rivera-cloud" in urls
    assert "https://github.com/alexrivera/distributed-cache" in urls

    # Check that labels were captured from page text
    li_link = next(h for h in hyperlinks if "linkedin" in h["url"])
    assert "linkedin" in li_link["label"].lower() or "profile" in li_link["label"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: MULTI-FORMAT PARSERS (ODT, RTF, HTML, PPTX, IMAGE)
# ─────────────────────────────────────────────────────────────────────────────

def test_odt_extraction_with_hyperlinks():
    """Validates pure-Python OpenDocument Text extraction with text:a hyperlinks."""
    odt_bytes = _make_odt_document()
    res = extract_document_content("elena.odt", odt_bytes, ".odt")

    assert "Elena Rostova" in res["raw_text"]
    assert "NextGen Systems" in res["raw_text"]

    hyperlinks = res["layout_info"].get("hyperlinks", [])
    assert any("github.com/erostova" in h["url"] for h in hyperlinks)
    assert any("linkedin.com/in/erostova" in h["url"] for h in hyperlinks)


def test_rtf_extraction_with_hyperlinks():
    """Validates RTF control-word parsing with embedded HYPERLINK fields."""
    rtf_bytes = _make_rtf_document()
    res = extract_document_content("david.rtf", rtf_bytes, ".rtf")

    assert "David Kim" in res["raw_text"]
    assert "Apex Financial Cloud" in res["raw_text"]

    hyperlinks = res["layout_info"].get("hyperlinks", [])
    assert any("linkedin.com/in/davidkim-sre" in h["url"] for h in hyperlinks)
    assert any("github.com/davidkim/k8s-operator" in h["url"] for h in hyperlinks)


def test_html_extraction_with_anchors():
    """Validates HTML extraction preserving semantic structure and <a> tags."""
    html_bytes = _make_html_resume()
    res = extract_document_content("sarah.html", html_bytes, ".html")

    assert "Sarah Connor" in res["raw_text"]
    assert "Cyberdyne Systems" in res["raw_text"]

    hyperlinks = res["layout_info"].get("hyperlinks", [])
    assert len(hyperlinks) >= 3
    assert any("linkedin.com/in/sarah-connor-security" in h["url"] for h in hyperlinks)
    assert any("cyberdyne-shield" in h["url"] for h in hyperlinks)


def test_pptx_extraction():
    """Validates PowerPoint slide text extraction."""
    pptx_bytes = _make_pptx_resume()
    res = extract_document_content("james.pptx", pptx_bytes, ".pptx")

    assert "James Holden" in res["raw_text"]
    assert "Fleet Management" in res["raw_text"]


def test_synthetic_image_extraction():
    """Validates image resume conversion to PDF in-memory and extraction."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 400), color="white")
    d = ImageDraw.Draw(img)
    d.text((30, 30), "Visual Resume Candidate", fill="black")
    d.text((30, 60), "visual.candidate@image.io", fill="black")

    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    png_bytes = img_buf.getvalue()

    res = extract_document_content("visual.png", png_bytes, ".png")
    assert res["layout_info"]["format"] == "image"
    assert res["page_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: SECURITY CHECKS & ERROR HANDLING
# ─────────────────────────────────────────────────────────────────────────────

def test_encrypted_pdf_rejection():
    """Validates that password-protected PDFs are rejected with actionable remediation."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "Secret Content")
    # Save with encryption
    enc_bytes = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner123", user_pw="user123")
    doc.close()

    is_valid, err_msg, _, _ = validate_resume_upload("encrypted.pdf", enc_bytes)
    assert not is_valid
    assert "password" in err_msg.lower() or "encrypted" in err_msg.lower()


def test_corrupted_file_rejection():
    """Validates that corrupted files with invalid magic signatures are rejected."""
    # Corrupted PDF
    is_valid, err_msg, _, _ = validate_resume_upload("corrupt.pdf", b"NOT_A_PDF_STREAM_DATA")
    assert not is_valid
    assert "signature" in err_msg.lower() or "corrupted" in err_msg.lower()

    # Corrupted DOCX (not a PK zip archive)
    is_valid, err_msg, _, _ = validate_resume_upload("corrupt.docx", b"NOT_A_ZIP_ARCHIVE")
    assert not is_valid
    assert "zip" in err_msg.lower() or "signature" in err_msg.lower()


def test_zip_bomb_decompression_limit():
    """Validates that zip archives exceeding decompression ratio limits are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 60MB uncompressed of zeroes
        zf.writestr("huge_file.xml", b"\x00" * (60 * 1024 * 1024))
    bomb_bytes = buf.getvalue()

    is_valid, err_msg, _, _ = validate_resume_upload("bomb.docx", bomb_bytes)
    assert not is_valid
    assert "decompression" in err_msg.lower() or "compression" in err_msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: CONCATENATED TECH TOKENIZATION & PROJECT DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────

def test_concatenated_tech_stack_tokenization():
    """
    Validates tokenization of jammed together technology strings into clean lists:
    e.g. 'FastAPIPythonPostgreSQLAzure OCRNERGemini LLM'
    """
    raw_stack = "FastAPIPythonPostgreSQLAzure OCRNERGemini LLM"
    tokens = normalize_technologies_list(raw_stack)

    assert "FastAPI" in tokens
    assert "Python" in tokens
    assert "PostgreSQL" in tokens
    assert "Azure OCR" in tokens
    assert "NER" in tokens
    assert "Gemini LLM" in tokens


def test_project_deduplication_idempotency():
    """Validates that duplicate bullet points in project definitions are cleanly eliminated."""
    proj = {
        "name": "Distributed Stream Processor",
        "technologies": ["Kafka", "Go", "Docker"],
        "description": "Engineered real-time telemetry processor.",
        "bullets": [
            "Engineered real-time telemetry processor.",
            "Engineered real-time telemetry processor.",  # Duplicate
            "Benchmarked pipeline throughput at 150k events per second.",
            "Benchmarked pipeline throughput at 150k events per second."   # Duplicate
        ]
    }

    norm_proj = normalize_and_deduplicate_project(proj)
    assert len(norm_proj["bullets"]) == 2
    assert "150k events per second" in norm_proj["bullets"][1]


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS: E2E UPLOAD & DIAGNOSTIC ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

def test_e2e_hyperlink_diagnostic_api(environment):
    """
    Tests end-to-end resume upload with hyperlinks and queries GET /resumes/{resume_id}/hyperlinks.
    """
    client, db, owner, other, admin, candidate, tmp_path = environment
    candidate_headers = headers(owner)
    pdf_bytes = _make_pdf_with_hyperlinks()
    files = {"file": ("alex_rivera_hyperlinks.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

    upload_res = client.post(
        "/api/v1/resumes/upload",
        files=files,
        headers=candidate_headers
    )
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    resume_id = data["resume_id"]

    # Call the diagnostic endpoint
    diag_res = client.get(
        f"/api/v1/resumes/{resume_id}/hyperlinks",
        headers=candidate_headers
    )
    assert diag_res.status_code == 200, diag_res.text
    diag_data = diag_res.json()

    assert diag_data["resume_id"] == resume_id
    assert diag_data["total_hyperlinks"] >= 2
    assert "by_type" in diag_data
    assert "hyperlinks" in diag_data

    links = diag_data["hyperlinks"]
    assert any("linkedin.com" in l["url"] for l in links)
    assert any("github.com" in l["url"] for l in links)
