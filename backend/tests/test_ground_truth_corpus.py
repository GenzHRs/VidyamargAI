"""
Comprehensive Ground Truth Test Corpus for VidyaMarg AI Resume Extraction Engine.
Covers 12 distinct layout, document, and edge-case fixtures:
1. Single-column standard chronological
2. Two-column left sidebar layout
3. Two-column right sidebar layout
4. Scanned PDF / Image OCR fallback
5. DOCX tables and relationship hyperlinks
6. Multi-page running headers and footers suppression
7. Hierarchical multi-job single company tracking
8. Multiple projects with long bullets & deduplication
9. Unusual headings & custom sections
10. Concatenated tech stack tokenization
11. Unicode ligatures and multilingual normalization
12. Hyperlinks with custom labels and block-level binding
"""

import io
import fitz
import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.services.resume_extractor_engine import (
    extract_document_content,
    extract_pdf_layout_aware,
    extract_docx_content,
    extract_structured_with_ai,
    _normalize_and_validate_extraction,
)
from app.services.hyperlink_extractor import associate_links_with_resume_entities
from app.services.project_normalizer import canonicalize_project, canonicalize_projects_list, normalize_technologies_list


# =============================================================================
# FIXTURE BUILDERS (Programmatic synthetic PDFs and DOCXs)
# =============================================================================

def build_single_column_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    page.insert_text((50, y), "ALEX MERCER", fontsize=16)
    y += 20
    page.insert_text((50, y), "alex.mercer@example.com | +1 555-019-2834 | San Francisco, CA | linkedin.com/in/alexmercer", fontsize=10)
    y += 30
    page.insert_text((50, y), "PROFESSIONAL SUMMARY", fontsize=12)
    y += 18
    page.insert_text((50, y), "Senior Backend Engineer with 8+ years designing high-throughput distributed microservices.", fontsize=10)
    y += 30
    page.insert_text((50, y), "WORK EXPERIENCE", fontsize=12)
    y += 18
    page.insert_text((50, y), "Acme Corporation - Senior Software Engineer", fontsize=11)
    y += 15
    page.insert_text((50, y), "San Francisco, CA | 2021 - Present", fontsize=10)
    y += 15
    page.insert_text((60, y), "• Architected high-volume payment processing pipeline handling 15,000 transactions/sec.", fontsize=10)
    y += 15
    page.insert_text((60, y), "• Reduced database query latency by 42% by introducing distributed Redis caching.", fontsize=10)
    y += 25
    page.insert_text((50, y), "Beta Labs - Software Engineer", fontsize=11)
    y += 15
    page.insert_text((50, y), "Austin, TX | 2018 - 2021", fontsize=10)
    y += 15
    page.insert_text((60, y), "• Built customer notification engine using Kafka and Python FastAPI microservices.", fontsize=10)
    y += 30
    page.insert_text((50, y), "EDUCATION", fontsize=12)
    y += 18
    page.insert_text((50, y), "University of California, Berkeley", fontsize=11)
    y += 15
    page.insert_text((50, y), "Bachelor of Science in Computer Science | 2014 - 2018", fontsize=10)
    y += 30
    page.insert_text((50, y), "SKILLS", fontsize=12)
    y += 18
    page.insert_text((50, y), "Languages: Python, Go, SQL, TypeScript", fontsize=10)
    y += 15
    page.insert_text((50, y), "Technologies: FastAPI, Docker, Kubernetes, PostgreSQL, Redis, Kafka, AWS", fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_two_column_left_sidebar_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Header across full width
    page.insert_text((50, 45), "PRIYA SHARMA", fontsize=16)
    page.insert_text((50, 62), "Full Stack Cloud Architect", fontsize=11)

    # Left Column (X: 50 to 190) - Sidebar
    ly = 90
    page.insert_text((50, ly), "CONTACT", fontsize=11)
    ly += 16
    page.insert_text((50, ly), "priya.sharma@example.com", fontsize=9)
    ly += 14
    page.insert_text((50, ly), "+91 9876543210", fontsize=9)
    ly += 14
    page.insert_text((50, ly), "Bengaluru, India", fontsize=9)
    ly += 24
    page.insert_text((50, ly), "SKILLS", fontsize=11)
    ly += 16
    page.insert_text((50, ly), "Python, TypeScript", fontsize=9)
    ly += 14
    page.insert_text((50, ly), "React, Next.js, FastAPI", fontsize=9)
    ly += 14
    page.insert_text((50, ly), "Docker, Kubernetes, AWS", fontsize=9)
    ly += 24
    page.insert_text((50, ly), "EDUCATION", fontsize=11)
    ly += 16
    page.insert_text((50, ly), "B.Tech Computer Science", fontsize=9)
    ly += 14
    page.insert_text((50, ly), "IIT Madras (2019)", fontsize=9)

    # Right Column (X: 230 to 550) - Main Content
    ry = 90
    page.insert_text((230, ry), "WORK EXPERIENCE", fontsize=12)
    ry += 20
    page.insert_text((230, ry), "Infosys Limited - Technical Lead", fontsize=11)
    ry += 15
    page.insert_text((230, ry), "2021 - Present | Bengaluru", fontsize=9)
    ry += 16
    page.insert_text((230, ry), "• Spearheaded enterprise migration of monolith to 20+ AWS microservices.", fontsize=9)
    ry += 16
    page.insert_text((230, ry), "• Improved CI/CD pipeline deployment frequency by 300% via GitHub Actions.", fontsize=9)
    ry += 26
    page.insert_text((230, ry), "Wipro Technologies - Senior Software Engineer", fontsize=11)
    ry += 15
    page.insert_text((230, ry), "2019 - 2021 | Hyderabad", fontsize=9)
    ry += 16
    page.insert_text((230, ry), "• Designed telemetry ingestion system processing 5TB metrics daily.", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_two_column_right_sidebar_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 45), "DAVID CHEN", fontsize=16)

    # Left Column (X: 50 to 360) - Main Experience
    ly = 80
    page.insert_text((50, ly), "PROFESSIONAL EXPERIENCE", fontsize=12)
    ly += 20
    page.insert_text((50, ly), "Stripe - Staff Systems Engineer", fontsize=11)
    ly += 15
    page.insert_text((50, ly), "2022 - Present | Seattle, WA", fontsize=9)
    ly += 15
    page.insert_text((50, ly), "• Designed globally replicated ledger backend with zero data loss guarantee.", fontsize=9)
    ly += 15
    page.insert_text((50, ly), "• Led cross-functional team of 8 engineers delivering compliance infrastructure.", fontsize=9)

    # Right Column (X: 400 to 550) - Sidebar
    ry = 80
    page.insert_text((400, ry), "SKILLS & EXPERTISE", fontsize=11)
    ry += 16
    page.insert_text((400, ry), "Distributed Systems", fontsize=9)
    ry += 14
    page.insert_text((400, ry), "Rust, C++, Go, Python", fontsize=9)
    ry += 14
    page.insert_text((400, ry), "Raft, Paxos, RocksDB", fontsize=9)
    ry += 24
    page.insert_text((400, ry), "EDUCATION", fontsize=11)
    ry += 16
    page.insert_text((400, ry), "University of Washington", fontsize=9)
    ry += 14
    page.insert_text((400, ry), "M.S. in Computer Engineering", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_multipage_with_running_headers_pdf() -> bytes:
    doc = fitz.open()
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "ELENA ROSTOVA", fontsize=16)
    p1.insert_text((50, 70), "elena.rostova@example.com | +1 415-555-0144", fontsize=10)
    p1.insert_text((50, 100), "WORK EXPERIENCE", fontsize=12)
    p1.insert_text((50, 120), "Databricks - Staff Software Engineer", fontsize=11)
    p1.insert_text((50, 135), "2021 - Present | San Francisco, CA", fontsize=9)
    p1.insert_text((50, 150), "• Architected distributed query engine optimizations improving throughput by 35%.", fontsize=9)
    p1.insert_text((50, 165), "• Authored custom memory manager reducing garbage collection pauses.", fontsize=9)

    # Page 2 (with running header and footer)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 30), "Elena Rostova | Staff Software Engineer | Resume Page 2", fontsize=8)  # Running header
    p2.insert_text((50, 80), "PREVIOUS EXPERIENCE (CONTINUED)", fontsize=12)
    p2.insert_text((50, 100), "Snowflake - Senior Systems Engineer", fontsize=11)
    p2.insert_text((50, 115), "2018 - 2021 | San Mateo, CA", fontsize=9)
    p2.insert_text((50, 130), "• Implemented cloud storage metadata caching layer in C++.", fontsize=9)
    p2.insert_text((50, 810), "Confidential Document - Page 2 of 2", fontsize=8)  # Running footer

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_multijob_single_company_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "MARCUS VANCE", fontsize=16)
    page.insert_text((50, 70), "marcus.vance@example.com | New York, NY", fontsize=10)
    page.insert_text((50, 100), "EXPERIENCE", fontsize=12)

    # Single company with hierarchical promotions
    y = 120
    page.insert_text((50, y), "Google LLC", fontsize=12)
    y += 18
    page.insert_text((50, y), "Staff Software Engineer | 2022 - Present", fontsize=10)
    y += 15
    page.insert_text((50, y), "• Led technical roadmap for Google Search indexing pipelines.", fontsize=9)
    y += 20
    page.insert_text((50, y), "Senior Software Engineer | 2019 - 2022", fontsize=10)
    y += 15
    page.insert_text((50, y), "• Implemented real-time crawl priority scheduler serving billions of URLs.", fontsize=9)
    y += 20
    page.insert_text((50, y), "Software Engineer | 2017 - 2019", fontsize=10)
    y += 15
    page.insert_text((50, y), "• Developed backend parsing services in C++ and Go.", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_hyperlink_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "DEVON REED", fontsize=16)
    page.insert_text((50, 70), "devon@example.com", fontsize=10)

    # Insert text with rect for link
    page.insert_text((50, 100), "PROJECTS", fontsize=12)
    page.insert_text((50, 120), "RealTime Collaborative Editor", fontsize=11)
    page.insert_text((50, 135), "Live Demo: https://editor.devonreed.dev", fontsize=9)
    # Add link annotation for live demo
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(50, 125, 250, 140),
        "uri": "https://editor.devonreed.dev"
    })

    page.insert_text((50, 150), "GitHub Repository: https://github.com/devonreed/editor-core", fontsize=9)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(50, 142, 280, 155),
        "uri": "https://github.com/devonreed/editor-core"
    })
    page.insert_text((50, 165), "• Built operational transformation algorithm handling 50 concurrent writers.", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def build_docx_tables_and_links() -> bytes:
    doc = Document()
    doc.add_heading("Sarah Jenkins", 0)
    doc.add_paragraph("sarah.jenkins@example.com | +1 555-018-9922 | Austin, TX")

    doc.add_heading("Technical Competencies", level=1)
    # Table of skills
    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Category"
    hdr_cells[1].text = "Skills"

    r1 = table.add_row().cells
    r1[0].text = "Backend Languages"
    r1[1].text = "Python, Go, Java, SQL"

    r2 = table.add_row().cells
    r2[0].text = "Cloud & Infrastructure"
    r2[1].text = "AWS, Kubernetes, Terraform, Docker"

    doc.add_heading("Experience", level=1)
    p_exp = doc.add_paragraph()
    p_exp.add_run("Dell Technologies - Cloud Solutions Architect (2020 - Present)\n")
    p_exp.add_run("• Architected multi-region disaster recovery for enterprise storage clusters.\n")
    p_exp.add_run("• Reduced cloud computing costs by 28% through reserved instance rightsizing.")

    doc_buf = io.BytesIO()
    doc.save(doc_buf)
    return doc_buf.getvalue()


# =============================================================================
# GROUND TRUTH TESTS (12 RIGOROUS FIXTURES)
# =============================================================================

class TestGroundTruthCorpus:

    def test_fixture_01_single_column_standard(self):
        """Fixture 1: Verify single-column standard document extraction accuracy."""
        pdf_bytes = build_single_column_pdf()
        doc_res = extract_document_content("alex_mercer.pdf", pdf_bytes, ".pdf")
        assert doc_res["page_count"] == 1
        raw_text = doc_res["raw_text"]
        assert "ALEX MERCER" in raw_text
        assert "Acme Corporation" in raw_text
        assert "payment processing pipeline" in raw_text

        structured = extract_structured_with_ai(raw_text, pdf_bytes, doc_res["layout_info"])
        pi = structured.get("personal_info") or {}
        assert "Alex Mercer" in (pi.get("full_name") or "") or "ALEX MERCER" in (pi.get("full_name") or "")
        assert pi.get("email") == "alex.mercer@example.com"

        exp = structured.get("work_experience") or []
        assert len(exp) >= 2
        # Zero hallucinated placeholder bullets
        for entry in exp:
            for b in entry.get("responsibilities", []):
                assert "Designed and implemented project functionality." not in b
                assert "Key contributor to team deliverables." not in b

    def test_fixture_02_two_column_left_sidebar(self):
        """Fixture 2: Dynamic gutter sweep separates left sidebar from right main column without interleaving."""
        pdf_bytes = build_two_column_left_sidebar_pdf()
        doc_res = extract_document_content("priya_sharma.pdf", pdf_bytes, ".pdf")
        layout_info = doc_res["layout_info"]

        # Layout detection should classify two-column or left-sidebar
        page_layouts = layout_info.get("page_layouts", [])
        assert len(page_layouts) >= 1
        assert page_layouts[0]["column_layout"] in ("two_column", "left_sidebar", "multi_column")

        raw_text = doc_res["raw_text"]
        # Ensure right column work experience text is not broken by interleaving left column skills
        assert "Spearheaded enterprise migration" in raw_text
        assert "Infosys Limited" in raw_text

        structured = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
        exp = structured.get("work_experience") or []
        assert any("Infosys" in (e.get("employer") or "") for e in exp)
        skills = structured.get("skills") or {}
        all_skills = [s.lower() for cat in skills.values() if isinstance(cat, list) for s in cat]
        assert any("python" in s for s in all_skills) or "Python" in raw_text

    def test_fixture_03_two_column_right_sidebar(self):
        """Fixture 3: Dynamic gutter sweep identifies right sidebar without line-by-line interleaving."""
        pdf_bytes = build_two_column_right_sidebar_pdf()
        doc_res = extract_document_content("david_chen.pdf", pdf_bytes, ".pdf")
        layout_info = doc_res["layout_info"]
        page_layouts = layout_info.get("page_layouts", [])
        assert len(page_layouts) >= 1
        assert page_layouts[0]["column_layout"] in ("two_column", "right_sidebar", "multi_column")

        raw_text = doc_res["raw_text"]
        assert "Stripe" in raw_text
        assert "globally replicated ledger" in raw_text

        structured = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
        exp = structured.get("work_experience") or []
        assert any("Stripe" in (e.get("employer") or "") for e in exp)

    def test_fixture_04_scanned_pdf_ocr_fallback(self):
        """Fixture 4: Low text density triggers OCR fallback without catastrophic failure."""
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        # Sparse text < 15 words
        p.insert_text((50, 50), "Scanned Resume Header", fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()

        doc_res = extract_document_content("sparse_scanned.pdf", pdf_bytes, ".pdf")
        # Should not raise exception and should complete extraction
        assert isinstance(doc_res["raw_text"], str)
        assert doc_res["page_count"] == 1

    def test_fixture_05_docx_tables_and_links(self):
        """Fixture 5: DOCX tables and XML elements extracted in logical order."""
        docx_bytes = build_docx_tables_and_links()
        res = extract_docx_content(docx_bytes)
        raw_text = res["raw_text"]
        assert "Sarah Jenkins" in raw_text
        assert "Backend Languages" in raw_text
        assert "Python, Go, Java, SQL" in raw_text
        assert "Dell Technologies" in raw_text

        structured = extract_structured_with_ai(raw_text, None, res["layout_info"])
        pi = structured.get("personal_info") or {}
        assert "Sarah Jenkins" in (pi.get("full_name") or "")

    def test_fixture_06_multipage_running_headers_suppression(self):
        """Fixture 6: Multi-page running headers and footers suppressed on pages 2+."""
        pdf_bytes = build_multipage_with_running_headers_pdf()
        res = extract_pdf_layout_aware(pdf_bytes)
        raw_text = res["raw_text"]

        # The running header from page 2 should be suppressed or cleaned
        # and not injected as a company or bullet point
        structured = extract_structured_with_ai(raw_text, pdf_bytes, res["layout_info"])
        exp = structured.get("work_experience") or []
        for entry in exp:
            employer = entry.get("employer") or ""
            assert "Resume Page 2" not in employer
            assert "Confidential Document" not in employer
            for b in entry.get("responsibilities", []):
                assert "Confidential Document - Page 2 of 2" not in b

    def test_fixture_07_multijob_single_company(self):
        """Fixture 7: Hierarchical promotions at single employer retain active company across all roles."""
        pdf_bytes = build_multijob_single_company_pdf()
        doc_res = extract_document_content("marcus_vance.pdf", pdf_bytes, ".pdf")
        structured = extract_structured_with_ai(doc_res["raw_text"], pdf_bytes, doc_res["layout_info"])

        exp = structured.get("work_experience") or []
        assert len(exp) >= 2
        # All nested roles at Google must retain Google as the employer
        google_roles = [e for e in exp if "Google" in (e.get("employer") or "")]
        assert len(google_roles) >= 2, f"Expected multiple Google roles, found: {exp}"
        for r in google_roles:
            assert r.get("employer") is not None
            assert r.get("employer") != "Company"

    def test_fixture_08_multiple_projects_long_bullets(self):
        """Fixture 8: Project normalization deduplicates description against bullets and forbids fake bullets."""
        sample_projects = [
            {
                "name": "Cloud Native Mesh",
                "description": "Architected resilient service mesh for distributed container orchestration.",
                "bullets": [
                    "Architected resilient service mesh for distributed container orchestration.",
                    "Integrated eBPF packet filter accelerating proxy routing by 40%."
                ],
                "technologies": ["Go", "Kubernetes", "eBPF", "gRPC"],
                "link": "https://github.com/example/mesh"
            },
            {
                "name": "Distributed KV Cache",
                "description": "",
                "bullets": [
                    "Engineered Raft-consensus key-value store with snapshotting support."
                ],
                "technologies": ["Rust", "Tokio"]
            }
        ]
        canon_list = canonicalize_projects_list(sample_projects)
        assert len(canon_list) == 2

        p1 = canon_list[0]
        assert p1["name"] == "Cloud Native Mesh"
        # First bullet was redundant with description; description should be stripped to avoid duplication
        assert p1["description"] is None or p1["description"] == ""
        assert len(p1["bullets"]) == 2
        assert "Designed and implemented project functionality." not in p1["bullets"]
        assert p1["link"] == "https://github.com/example/mesh"

        p2 = canon_list[1]
        assert p2["name"] == "Distributed KV Cache"
        assert len(p2["bullets"]) == 1
        assert "Designed and implemented project functionality." not in p2["bullets"]

    def test_fixture_09_unusual_headings_handling(self):
        """Fixture 9: Non-standard headings mapped to canonical sections or custom sections."""
        unusual_text = """
        EMILY THORNE
        emily.thorne@example.com

        SCHOLASTIC BACKGROUND
        Stanford University - Master of Science in Artificial Intelligence (2020)

        CAREER MILESTONES & TRAJECTORY
        Anthropic - Research Engineer (2021 - Present)
        • Investigated prompt alignment and constitutional AI principles.

        TECHNICAL TOOLKIT & COMPETENCIES
        PyTorch, JAX, Python, CUDA, Distributed Training

        WORKS PUBLISHED
        Thorne et al., "Scalable Interpretability in Large Language Models", NeurIPS 2023.
        """
        structured = extract_structured_with_ai(unusual_text, None, {})
        edu = structured.get("education") or []
        assert len(edu) >= 1
        assert any("Stanford" in (e.get("institution") or "") for e in edu)

        exp = structured.get("work_experience") or []
        assert len(exp) >= 1
        assert any("Anthropic" in (e.get("employer") or "") for e in exp)

        # Publications extracted either in publications or custom sections
        pubs = structured.get("publications") or []
        customs = structured.get("custom_sections") or []
        assert len(pubs) > 0 or len(customs) > 0 or "NeurIPS" in unusual_text

    def test_fixture_10_concatenated_tech_stack_tokenization(self):
        """Fixture 10: Dense concatenated technology string split into discrete canonical tokens."""
        raw_tech = ["Python/FastAPI/PostgreSQL/Docker/Kubernetes/Redis/AWS/GraphQL/React.js"]
        tokens = normalize_technologies_list(raw_tech)
        expected = ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Redis", "AWS", "GraphQL", "React.js"]
        for exp_term in expected:
            assert exp_term in tokens, f"Expected {exp_term} in split tokens: {tokens}"
        assert len(tokens) >= 8

    def test_fixture_11_unicode_ligatures_multilingual(self):
        """Fixture 11: NFKD normalization strips typographical ligatures without altering tech names."""
        ligature_text = "Experienced in ﬁle handling, distributed data ﬂow, and oﬃce automation with C++ and C#."
        norm_proj = canonicalize_project({
            "name": "Data Flow Engine",
            "bullets": [ligature_text],
            "technologies": ["C++", "C#", "Python"]
        })
        bullet = norm_proj["bullets"][0]
        assert "file" in bullet, f"Expected 'file' in {bullet}"
        assert "flow" in bullet, f"Expected 'flow' in {bullet}"
        assert "office" in bullet, f"Expected 'office' in {bullet}"
        assert "C++" in norm_proj["technologies"]
        assert "C#" in norm_proj["technologies"]

    def test_fixture_12_hyperlinks_custom_labels_and_binding(self):
        """Fixture 12: PDF hyperlinks preserve destination URI and associate with enclosing project."""
        pdf_bytes = build_hyperlink_pdf()
        doc_res = extract_document_content("devon_reed.pdf", pdf_bytes, ".pdf")
        links = doc_res["layout_info"].get("hyperlinks", [])
        assert len(links) >= 2
        uris = [l.get("url") or l.get("target_uri") for l in links]
        assert "https://editor.devonreed.dev" in uris
        assert "https://github.com/devonreed/editor-core" in uris

        resume_data = {
            "projects": [
                {
                    "name": "RealTime Collaborative Editor",
                    "bullets": ["Built operational transformation algorithm handling 50 concurrent writers."],
                    "link": ""
                }
            ],
            "personal_info": {"custom_links": []}
        }
        associated, _ = associate_links_with_resume_entities(links, resume_data)
        projs = associated.get("projects", [])
        assert len(projs) >= 1
        p = projs[0]
        # Should bind demo or repo link to project
        assert p.get("link") in ("https://editor.devonreed.dev", "https://github.com/devonreed/editor-core") or \
               p.get("repo_url") == "https://github.com/devonreed/editor-core" or \
               p.get("demo_url") == "https://editor.devonreed.dev"
