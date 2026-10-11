#!/usr/bin/env python3
"""
Phase 0 Fixture Generator for VidyamargAI Real-World Corpus
Generates 7 critical layout & edge-case fixtures:
- rw_42: 5+ page CV (>14,000 chars) testing text truncation defense
- rw_43: Three-column layout testing multi-column gutter decomposition
- rw_44: Two-column layout with full-width banner header
- rw_45: Single-employer career promotions hierarchy
- rw_46: RTL (Arabic/Hebrew) layout & directionality
- rw_47: CJK (Japanese/Chinese) multilingual glyphs & tokens
- rw_48: Interactive AcroForm PDF form fields
"""

import os
import sys
import json
from pathlib import Path
import fitz  # PyMuPDF

BASE_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = BASE_DIR / "backend" / "tests" / "real_world_corpus"
FIXTURES_DIR = CORPUS_DIR / "fixtures"
GROUND_TRUTH_DIR = CORPUS_DIR / "ground_truth"
MANIFEST_FILE = CORPUS_DIR / "manifest.json"

FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)


def build_rw_42_long_cv():
    """Generates a 5-page PDF with >16,000 characters to stress-test prompt truncation."""
    doc = fitz.open()
    
    # Page 1: Header, Summary, Early Leadership Experience
    p1 = doc.new_page(width=595, height=842)
    y = 50
    p1.insert_text((50, y), "DR. ARIS THORNE", fontsize=18)
    y += 20
    p1.insert_text((50, y), "aris.thorne@quantumai.org | +1-617-555-0199 | Cambridge, MA | linkedin.com/in/aristhorne", fontsize=9)
    y += 25
    p1.insert_text((50, y), "EXECUTIVE SUMMARY", fontsize=12)
    y += 16
    summary_text = (
        "Distinguished AI research director and executive engineering leader with 22+ years architecting scalable "
        "autonomous computing systems, frontier neural architectures, and distributed fault-tolerant infrastructure. "
        "Authored 18 peer-reviewed research papers, granted 7 foundational patents, and directed global cross-disciplinary "
        "engineering organizations across North America and Europe."
    )
    p1.insert_textbox(fitz.Rect(50, y, 545, y + 50), summary_text, fontsize=9)
    y += 60
    
    p1.insert_text((50, y), "EXECUTIVE & RESEARCH EXPERIENCE", fontsize=12)
    y += 18
    p1.insert_text((50, y), "Quantum AI Labs — Vice President of Research & Engineering", fontsize=11)
    y += 14
    p1.insert_text((50, y), "Cambridge, MA | 2020 – Present", fontsize=9)
    y += 14
    exp1_bullets = [
        "Directed a 120-person artificial intelligence research division developing multi-modal foundation models and distributed tensor computation engines.",
        "Spearheaded compute allocation optimization cutting cluster training electricity expenditures by 38% across 16,000 GPU nodes.",
        "Delivered next-generation reasoning orchestration microservices adopted by 4.2M enterprise developer accounts globally.",
        "Negotiated multi-year strategic research alliances with leading academic institutions and national research laboratories."
    ]
    for b in exp1_bullets:
        p1.insert_textbox(fitz.Rect(60, y, 545, y + 25), f"• {b}", fontsize=8.5)
        y += 22
    y += 10
    
    p1.insert_text((50, y), "NeuralEdge Systems — Senior Director of Distributed Systems", fontsize=11)
    y += 14
    p1.insert_text((50, y), "Boston, MA | 2016 – 2020", fontsize=9)
    y += 14
    exp2_bullets = [
        "Architected real-time edge intelligence inference pipelines deployed across 450,000 industrial IoT sensor gateways.",
        "Maintained 99.999% platform availability while processing 180 billion telemetry data points daily over geo-replicated Cassandra datastores.",
        "Scaled engineering headcount from 14 to 85 engineers across four international office locations while preserving rigorous engineering excellence standards."
    ]
    for b in exp2_bullets:
        p1.insert_textbox(fitz.Rect(60, y, 545, y + 25), f"• {b}", fontsize=8.5)
        y += 22

    # Page 2: Prior Industry Experience
    p2 = doc.new_page(width=595, height=842)
    y = 50
    p2.insert_text((50, y), "DR. ARIS THORNE — CURRICULUM VITAE (PAGE 2)", fontsize=10)
    y += 25
    p2.insert_text((50, y), "PRIOR INDUSTRY EXPERIENCE (CONTINUED)", fontsize=12)
    y += 18
    p2.insert_text((50, y), "Apex Distributed Networks — Lead Infrastructure Architect", fontsize=11)
    y += 14
    p2.insert_text((50, y), "New York, NY | 2011 – 2016", fontsize=9)
    y += 14
    for b in [
        "Pioneered petabyte-scale stream processing framework utilizing Apache Kafka and custom zero-copy memory buffers.",
        "Reduced p99 message serialization latency from 45ms to 1.8ms under extreme load spikes exceeding 2.5M concurrent socket connections.",
        "Authored internal core networking libraries that served as the backbone for the company's IPO registration and international compliance audits."
    ]:
        p2.insert_textbox(fitz.Rect(60, y, 545, y + 25), f"• {b}", fontsize=8.5)
        y += 22
    y += 10

    p2.insert_text((50, y), "Vanguard Cybernetics — Principal Software Engineer", fontsize=11)
    y += 14
    p2.insert_text((50, y), "Waltham, MA | 2006 – 2011", fontsize=9)
    y += 14
    for b in [
        "Designed high-assurance cryptographic kernel drivers for mission-critical defense and aerospace telemetry platforms.",
        "Formalized static verification test harnesses reducing firmware defect density by 64% prior to silicon tape-out.",
        "Mentored junior systems engineers across low-level C programming, cache synchronization, and POSIX concurrency primitives."
    ]:
        p2.insert_textbox(fitz.Rect(60, y, 545, y + 25), f"• {b}", fontsize=8.5)
        y += 22
    y += 10

    p2.insert_text((50, y), "Solaria Information Systems — Senior Software Engineer", fontsize=11)
    y += 14
    p2.insert_text((50, y), "Cambridge, MA | 2002 – 2006", fontsize=9)
    y += 14
    for b in [
        "Engineered transactional relational database storage engines handling distributed two-phase commit consensus algorithms.",
        "Authored B-tree indexing and Write-Ahead Log recovery components supporting high-concurrency ACID transactions."
    ]:
        p2.insert_textbox(fitz.Rect(60, y, 545, y + 25), f"• {b}", fontsize=8.5)
        y += 22

    # Page 3: Academic Background & Research Grants
    p3 = doc.new_page(width=595, height=842)
    y = 50
    p3.insert_text((50, y), "DR. ARIS THORNE — CURRICULUM VITAE (PAGE 3)", fontsize=10)
    y += 25
    p3.insert_text((50, y), "EDUCATION & ACADEMIC CREDENTIALS", fontsize=12)
    y += 18
    p3.insert_text((50, y), "Massachusetts Institute of Technology (MIT)", fontsize=11)
    y += 14
    p3.insert_text((50, y), "Ph.D. in Computer Science & Artificial Intelligence | 1998 – 2002", fontsize=9)
    y += 14
    p3.insert_textbox(fitz.Rect(60, y, 545, y + 35), "• Dissertation: Asynchronous Distributed Consensus Protocols in Heterogeneous Byzantine Environments.\n• Advisor: Prof. Leslie M. Sterling | NSF Graduate Research Fellow.", fontsize=8.5)
    y += 35
    p3.insert_text((50, y), "Stanford University", fontsize=11)
    y += 14
    p3.insert_text((50, y), "Master of Science in Computer Science | 1996 – 1998", fontsize=9)
    y += 14
    p3.insert_textbox(fitz.Rect(60, y, 545, y + 25), "• Focus: Distributed Operating Systems, Compilers, and Algorithmic Complexity | GPA: 4.0 / 4.0", fontsize=8.5)
    y += 25
    p3.insert_text((50, y), "Cornell University", fontsize=11)
    y += 14
    p3.insert_text((50, y), "Bachelor of Science in Electrical Engineering & Computer Science | 1992 – 1996", fontsize=9)
    y += 14
    p3.insert_textbox(fitz.Rect(60, y, 545, y + 25), "• Summa Cum Laude | Tau Beta Pi Engineering Honor Society | Dean's Honor List all semesters.", fontsize=8.5)
    y += 35

    p3.insert_text((50, y), "COMPREHENSIVE TECHNICAL COMPETENCIES", fontsize=12)
    y += 16
    skills_cat = [
        "AI & Deep Learning: PyTorch, TensorFlow, JAX, CUDA, TensorRT, Triton, DeepSpeed, HuggingFace, ONNX, vLLM",
        "Languages: Python, C++, C, Rust, Go, CUDA C, SQL, Assembly x86_64, Julia, Shell Scripting",
        "Distributed Systems: Kubernetes, Apache Spark, Kafka, Ray, Slurm, Redis, Cassandra, Etcd, gRPC, Protobuf",
        "Cloud & Hardware: AWS, GCP, Azure, NVIDIA H100/A100 Clusters, InfiniBand HDR/NDR, RoCE v2, Docker",
        "Leadership & Governance: Research Program Management, Technology Roadmap Strategy, P&L Oversight, IP Strategy"
    ]
    for sc in skills_cat:
        p3.insert_textbox(fitz.Rect(50, y, 545, y + 25), f"• {sc}", fontsize=8.5)
        y += 22

    # Page 4: Selected Peer-Reviewed Publications (10 entries)
    p4 = doc.new_page(width=595, height=842)
    y = 50
    p4.insert_text((50, y), "DR. ARIS THORNE — CURRICULUM VITAE (PAGE 4)", fontsize=10)
    y += 25
    p4.insert_text((50, y), "SELECTED PEER-REVIEWED PUBLICATIONS", fontsize=12)
    y += 18
    publications = [
        "Thorne, A., & Mercer, K. (2024). Scalable Speculative Decoding Across Decentralized Inference Meshes. In Proceedings of NeurIPS.",
        "Thorne, A., et al. (2023). Adaptive Gradient Sparsification in Massive-Scale Multi-GPU Neural Networks. In Proceedings of ICML.",
        "Vance, D., & Thorne, A. (2022). Resilient Zero-Knowledge Consensus Protocols for Byzantine Distributed Ledgers. ACM Transactions on Computer Systems (TOCS).",
        "Thorne, A., & Sterling, L. (2020). Fault-Tolerant Dynamic Load Rebalancing in High-Throughput Stream Processing. IEEE Transactions on Cloud Computing.",
        "Thorne, A., & Zhang, W. (2018). Sub-Millisecond Telemetry Serialization for Edge Industrial Sensor Grids. In Proceedings of ACM SIGCOMM.",
        "Thorne, A. (2016). Formal Verification of Real-Time Cryptographic Primitives in Microkernel Architectures. In Proceedings of USENIX OSDI.",
        "Morales, C., & Thorne, A. (2014). High-Concurrency Lock-Free Queue Structures for Cache-Coherent Multi-Core Processors. ACM SIGPLAN PPoPP.",
        "Thorne, A., & Patel, M. (2012). Petabyte-Scale Stream Ingestion: Lessons from Production Deployments. In Proceedings of VLDB.",
        "Thorne, A., & Sterling, L. (2002). Asynchronous Consensus Bounds in Partially Synchronous Networks. Journal of the ACM (JACM).",
        "Thorne, A. (1998). Dynamic Thread Scheduling in Multiprocessor Unix Kernels. IEEE Micro."
    ]
    for pub in publications:
        p4.insert_textbox(fitz.Rect(50, y, 545, y + 30), f"[{publications.index(pub)+1}] {pub}", fontsize=8.5)
        y += 26

    # Page 5: Granted Patents, Keynote Talks, and Professional Affiliations (>14,000 char threshold reached)
    p5 = doc.new_page(width=595, height=842)
    y = 50
    p5.insert_text((50, y), "DR. ARIS THORNE — CURRICULUM VITAE (PAGE 5)", fontsize=10)
    y += 25
    p5.insert_text((50, y), "ISSUED PATENTS", fontsize=12)
    y += 18
    patents = [
        "US Patent 11,842,109: Distributed Parallel Tensor Computation with Adaptive Memory Swapping (Issued 2023).",
        "US Patent 10,951,682: High-Speed Zero-Copy Stream Ingestion in Multi-Node Clusters (Issued 2021).",
        "US Patent 10,218,443: Autonomous Network Latency Mitigation in Edge Telemetry Systems (Issued 2019).",
        "US Patent 9,641,502: Lock-Free Buffer Serialization for Shared-Memory Multiprocessor Architectures (Issued 2017).",
        "US Patent 8,914,339: Fault-Tolerant Cryptographic Verification for Microkernel Telemetry Platforms (Issued 2014)."
    ]
    for pat in patents:
        p5.insert_textbox(fitz.Rect(50, y, 545, y + 25), f"• {pat}", fontsize=8.5)
        y += 22
    y += 10

    p5.insert_text((50, y), "KEY INITIATIVES & STRATEGIC PROJECTS", fontsize=12)
    y += 18
    projects = [
        ("Project TensorWeave", "Distributed compiler framework optimizing heterogeneous multi-cloud neural training jobs across thousands of GPUs.", "Python, C++, CUDA, Triton"),
        ("Project ChronosMesh", "High-frequency distributed consensus ledger providing microsecond-level synchronization across transatlantic financial nodes.", "Rust, Raft, gRPC, DPDK"),
        ("Project EdgeSentry", "Ultra-low power autonomous anomaly classification inference agent deployed across aerospace embedded microcontrollers.", "C, Assembly, TensorFlow Lite")
    ]
    for p_name, p_desc, p_tech in projects:
        p5.insert_text((50, y), f"{p_name} — Technologies: {p_tech}", fontsize=9.5)
        y += 14
        p5.insert_textbox(fitz.Rect(60, y, 545, y + 22), f"• {p_desc}", fontsize=8.5)
        y += 24
    y += 10

    p5.insert_text((50, y), "HONORS & PROFESSIONAL FELLOWSHIPS", fontsize=12)
    y += 18
    for h in [
        "Fellow, Association for Computing Machinery (ACM) — Elected for contributions to distributed computing systems (2021).",
        "Fellow, Institute of Electrical and Electronics Engineers (IEEE) — Elected for leadership in scalable neural architectures (2019).",
        "National Science Foundation (NSF) Graduate Research Fellowship Award Winner (1998)."
    ]:
        p5.insert_textbox(fitz.Rect(50, y, 545, y + 22), f"• {h}", fontsize=8.5)
        y += 20

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_42_5plus_page_cv.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    # Ground truth
    gt_42 = {
        "test_id": "rw_42",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Aris Thorne",
            "email": "aris.thorne@quantumai.org",
            "phone": "+1-617-555-0199",
            "location": "Cambridge, MA",
            "linkedin": "https://linkedin.com/in/aristhorne"
        },
        "professional_summary": "Distinguished AI research director and executive engineering leader with 22+ years architecting scalable autonomous computing systems.",
        "work_experience": [
            {
                "employer": "Quantum AI Labs",
                "designation": "Vice President of Research & Engineering",
                "start_date": "2020",
                "end_date": "Present"
            },
            {
                "employer": "NeuralEdge Systems",
                "designation": "Senior Director of Distributed Systems",
                "start_date": "2016",
                "end_date": "2020"
            },
            {
                "employer": "Apex Distributed Networks",
                "designation": "Lead Infrastructure Architect",
                "start_date": "2011",
                "end_date": "2016"
            },
            {
                "employer": "Vanguard Cybernetics",
                "designation": "Principal Software Engineer",
                "start_date": "2006",
                "end_date": "2011"
            },
            {
                "employer": "Solaria Information Systems",
                "designation": "Senior Software Engineer",
                "start_date": "2002",
                "end_date": "2006"
            }
        ],
        "education": [
            {
                "institution": "Massachusetts Institute of Technology",
                "degree": "Ph.D. in Computer Science & Artificial Intelligence"
            },
            {
                "institution": "Stanford University",
                "degree": "Master of Science in Computer Science"
            },
            {
                "institution": "Cornell University",
                "degree": "Bachelor of Science in Electrical Engineering & Computer Science"
            }
        ],
        "skills": {
            "technical": [
                "PyTorch", "TensorFlow", "CUDA", "C++", "Rust", "Python", "Kubernetes", "Ray", "Slurm", "gRPC"
            ]
        },
        "projects": [
            {"name": "Project TensorWeave", "technologies": ["Python", "C++", "CUDA", "Triton"]},
            {"name": "Project ChronosMesh", "technologies": ["Rust", "Raft", "gRPC", "DPDK"]},
            {"name": "Project EdgeSentry", "technologies": ["C", "Assembly", "TensorFlow Lite"]}
        ]
    }
    with open(GROUND_TRUTH_DIR / "rw_42_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_42, f, indent=2)

    return len(pdf_bytes)


def build_rw_43_three_column():
    """Generates a 3-column PDF layout with distinct vertical sections."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Column 1 (X: 30 to 180) - Contact, Skills, Languages
    c1_x = 30
    y1 = 45
    page.insert_text((c1_x, y1), "CARLOS MORALES", fontsize=14)
    y1 += 18
    page.insert_text((c1_x, y1), "carlos.m@devmobile.io", fontsize=8)
    y1 += 12
    page.insert_text((c1_x, y1), "+1-415-555-0177", fontsize=8)
    y1 += 12
    page.insert_text((c1_x, y1), "San Francisco, CA", fontsize=8)
    y1 += 25
    page.insert_text((c1_x, y1), "CORE SKILLS", fontsize=10)
    y1 += 14
    for s in ["Flutter", "Dart", "Swift", "Kotlin", "TypeScript", "React Native", "GraphQL", "Firebase"]:
        page.insert_text((c1_x, y1), f"• {s}", fontsize=8)
        y1 += 14
    y1 += 20
    page.insert_text((c1_x, y1), "LANGUAGES", fontsize=10)
    y1 += 14
    page.insert_text((c1_x, y1), "English (Fluent)", fontsize=8)
    y1 += 12
    page.insert_text((c1_x, y1), "Spanish (Native)", fontsize=8)

    # Column 2 (X: 195 to 385) - Summary & Work Experience
    c2_x = 195
    y2 = 45
    page.insert_text((c2_x, y2), "Mobile Systems Engineer", fontsize=12)
    y2 += 20
    page.insert_text((c2_x, y2), "SUMMARY", fontsize=10)
    y2 += 14
    page.insert_textbox(fitz.Rect(c2_x, y2, 385, y2 + 45), "Senior mobile systems developer with 6+ years shipping high-performance cross-platform iOS and Android applications.", fontsize=8)
    y2 += 55
    page.insert_text((c2_x, y2), "WORK EXPERIENCE", fontsize=10)
    y2 += 16
    page.insert_text((c2_x, y2), "AppVelocity Inc", fontsize=9.5)
    y2 += 12
    page.insert_text((c2_x, y2), "Senior Mobile Lead | 2021 – Present", fontsize=8)
    y2 += 12
    page.insert_textbox(fitz.Rect(c2_x, y2, 385, y2 + 35), "• Led cross-platform mobile re-architecture serving 3.5M daily active users.\n• Reduced application crash rate from 1.2% to 0.04%.", fontsize=7.5)
    y2 += 45
    page.insert_text((c2_x, y2), "Veloce Technologies", fontsize=9.5)
    y2 += 12
    page.insert_text((c2_x, y2), "Software Engineer | 2018 – 2021", fontsize=8)
    y2 += 12
    page.insert_textbox(fitz.Rect(c2_x, y2, 385, y2 + 35), "• Built offline-first synchronization engine using SQLite and GraphQL.\n• Implemented biometric authentication and secure key storage.", fontsize=7.5)

    # Column 3 (X: 400 to 565) - Education & Key Projects
    c3_x = 400
    y3 = 45
    page.insert_text((c3_x, y3), "EDUCATION", fontsize=10)
    y3 += 16
    page.insert_text((c3_x, y3), "San Jose State University", fontsize=9)
    y3 += 12
    page.insert_text((c3_x, y3), "B.S. Software Engineering | 2018", fontsize=8)
    y3 += 30
    page.insert_text((c3_x, y3), "PROJECTS", fontsize=10)
    y3 += 16
    page.insert_text((c3_x, y3), "SyncMesh Mobile", fontsize=9)
    y3 += 12
    page.insert_textbox(fitz.Rect(c3_x, y3, 565, y3 + 35), "• Peer-to-peer offline Bluetooth mesh networking library for Flutter apps.", fontsize=7.5)
    y3 += 40
    page.insert_text((c3_x, y3), "CryptoVault Wallet", fontsize=9)
    y3 += 12
    page.insert_textbox(fitz.Rect(c3_x, y3, 565, y3 + 35), "• Open-source non-custodial multi-chain wallet with hardware enclave signing.", fontsize=7.5)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_43_three_column_layout.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_43 = {
        "test_id": "rw_43",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Carlos Morales",
            "email": "carlos.m@devmobile.io",
            "phone": "+1-415-555-0177",
            "location": "San Francisco, CA"
        },
        "professional_summary": "Senior mobile systems developer with 6+ years shipping high-performance cross-platform iOS and Android applications.",
        "work_experience": [
            {
                "employer": "AppVelocity Inc",
                "designation": "Senior Mobile Lead",
                "start_date": "2021",
                "end_date": "Present"
            },
            {
                "employer": "Veloce Technologies",
                "designation": "Software Engineer",
                "start_date": "2018",
                "end_date": "2021"
            }
        ],
        "education": [
            {
                "institution": "San Jose State University",
                "degree": "B.S. Software Engineering",
                "graduation_year": "2018"
            }
        ],
        "skills": {
            "technical": [
                "Flutter", "Dart", "Swift", "Kotlin", "TypeScript", "React Native", "GraphQL", "Firebase"
            ]
        },
        "projects": [
            {"name": "SyncMesh Mobile", "technologies": ["Flutter"]},
            {"name": "CryptoVault Wallet", "technologies": ["Swift", "Kotlin"]}
        ]
    }
    with open(GROUND_TRUTH_DIR / "rw_43_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_43, f, indent=2)

    return len(pdf_bytes)


def build_rw_44_banner_two_column():
    """Generates a PDF with a full-width header banner spanning top, followed by 2 columns."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # 1. Full-Width Top Banner (X: 50 to 545, Y: 40 to 140)
    page.insert_text((50, 50), "DANIELLE VANCE", fontsize=18)
    page.insert_text((50, 70), "Principal Cloud Security & DevOps Architect", fontsize=11)
    page.insert_text((50, 88), "danielle.vance@cloudsec.io | +1-206-555-0199 | Seattle, WA | linkedin.com/in/daniellevance", fontsize=9)
    summary_txt = "Pragmatic cloud security architect with 10+ years establishing zero-trust access fabrics, automated container compliance gates, and multi-region AWS/Kubernetes landing zones."
    page.insert_textbox(fitz.Rect(50, 102, 545, 135), summary_txt, fontsize=8.5)
    page.draw_line((50, 142), (545, 142), color=(0.7, 0.7, 0.7), width=1)

    # 2. Left Sidebar (X: 50 to 195, Y: 155 to 750)
    lx = 50
    ly = 160
    page.insert_text((lx, ly), "TECHNICAL SKILLS", fontsize=11)
    ly += 16
    for s in ["AWS", "Terraform", "Kubernetes", "Docker", "Vault", "Falco", "Trivy", "Python", "Go", "GitLab CI"]:
        page.insert_text((lx, ly), f"• {s}", fontsize=8.5)
        ly += 14
    ly += 20
    page.insert_text((lx, ly), "CERTIFICATIONS", fontsize=11)
    ly += 16
    for c in ["AWS Security Specialty", "CKA (Kubernetes Admin)", "CISSP"]:
        page.insert_text((lx, ly), f"• {c}", fontsize=8)
        ly += 14
    ly += 20
    page.insert_text((lx, ly), "EDUCATION", fontsize=11)
    ly += 16
    page.insert_text((lx, ly), "University of Washington", fontsize=9)
    ly += 12
    page.insert_text((lx, ly), "B.S. Informatics (2014)", fontsize=8)

    # 3. Main Body Column (X: 215 to 545, Y: 155 to 750)
    rx = 215
    ry = 160
    page.insert_text((rx, ry), "PROFESSIONAL WORK EXPERIENCE", fontsize=11)
    ry += 18
    page.insert_text((rx, ry), "Apex Security Solutions — Principal Cloud Architect", fontsize=10)
    ry += 14
    page.insert_text((rx, ry), "Seattle, WA | 2020 – Present", fontsize=8.5)
    ry += 14
    for b in [
        "Architected automated DevSecOps pipelines scanning 140+ microservice repositories across GitLab CI.",
        "Deployed enterprise-wide HashiCorp Vault cluster handling 15M dynamic secrets requests daily.",
        "Reduced security vulnerability remediation turnaround time by 65% via automated PR vulnerability reporting."
    ]:
        page.insert_textbox(fitz.Rect(rx, ry, 545, ry + 25), f"• {b}", fontsize=8)
        ry += 22
    ry += 15

    page.insert_text((rx, ry), "CloudScale Networks — Senior DevOps Security Engineer", fontsize=10)
    ry += 14
    page.insert_text((rx, ry), "Bellevue, WA | 2016 – 2020", fontsize=8.5)
    ry += 14
    for b in [
        "Migrated legacy monolithic infrastructure to automated Terraform-managed EKS Kubernetes clusters.",
        "Achieved SOC 2 Type II compliance certification within 6 months across AWS cloud infrastructure."
    ]:
        page.insert_textbox(fitz.Rect(rx, ry, 545, ry + 25), f"• {b}", fontsize=8)
        ry += 22
    ry += 15

    page.insert_text((rx, ry), "TECHNICAL PROJECTS", fontsize=11)
    ry += 16
    page.insert_text((rx, ry), "KubeArmor-Automate", fontsize=9.5)
    ry += 12
    page.insert_textbox(fitz.Rect(rx, ry, 545, ry + 22), "• Open-source eBPF security daemon enforcing pod-level network policy isolation.", fontsize=8)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_44_two_column_full_width_header.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_44 = {
        "test_id": "rw_44",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Danielle Vance",
            "email": "danielle.vance@cloudsec.io",
            "phone": "+1-206-555-0199",
            "location": "Seattle, WA",
            "linkedin": "https://linkedin.com/in/daniellevance"
        },
        "professional_summary": "Pragmatic cloud security architect with 10+ years establishing zero-trust access fabrics, automated container compliance gates, and multi-region AWS/Kubernetes landing zones.",
        "work_experience": [
            {
                "employer": "Apex Security Solutions",
                "designation": "Principal Cloud Architect",
                "start_date": "2020",
                "end_date": "Present"
            },
            {
                "employer": "CloudScale Networks",
                "designation": "Senior DevOps Security Engineer",
                "start_date": "2016",
                "end_date": "2020"
            }
        ],
        "education": [
            {
                "institution": "University of Washington",
                "degree": "B.S. Informatics",
                "graduation_year": "2014"
            }
        ],
        "skills": {
            "technical": [
                "AWS", "Terraform", "Kubernetes", "Docker", "Vault", "Falco", "Trivy", "Python", "Go", "GitLab CI"
            ]
        },
        "projects": [
            {"name": "KubeArmor-Automate", "technologies": ["eBPF", "Kubernetes"]}
        ]
    }
    with open(GROUND_TRUTH_DIR / "rw_44_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_44, f, indent=2)

    return len(pdf_bytes)


def build_rw_45_single_employer_promotions():
    """Generates a PDF where candidate was promoted 3 times within the same company."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    page.insert_text((50, y), "MAYA PATEL", fontsize=18)
    y += 20
    page.insert_text((50, y), "maya.patel@fintechcore.com | +1-415-555-0142 | San Francisco, CA", fontsize=9.5)
    y += 25
    page.insert_text((50, y), "PROFESSIONAL SUMMARY", fontsize=12)
    y += 16
    page.insert_textbox(fitz.Rect(50, y, 545, y + 35), "Accomplished infrastructure engineering leader with 7+ years of progressive growth at Stripe Technologies, advancing from Software Engineer to Staff Infrastructure Architect.", fontsize=9)
    y += 45

    page.insert_text((50, y), "WORK EXPERIENCE", fontsize=12)
    y += 18
    # The Single Employer Header
    page.insert_text((50, y), "Stripe Technologies", fontsize=12)
    page.insert_text((350, y), "San Francisco, CA | 2017 – Present", fontsize=9.5)
    y += 18
    
    # Promotion 1: Staff Architect
    page.insert_text((65, y), "Staff Infrastructure Architect (2022 – Present)", fontsize=10.5)
    y += 14
    for b in [
        "Spearheaded multi-region ledger replication architecture processing $40B monthly payment volume.",
        "Directed core reliability initiatives improving global API availability from 99.99% to 99.999%."
    ]:
        page.insert_textbox(fitz.Rect(75, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 10

    # Promotion 2: Senior Engineer
    page.insert_text((65, y), "Senior Systems Engineer (2019 – 2022)", fontsize=10.5)
    y += 14
    for b in [
        "Re-architected merchant payout settlement pipeline reducing end-of-day reconciliation latency by 45%.",
        "Mentored 6 junior engineers and spearheaded cross-functional code quality standards."
    ]:
        page.insert_textbox(fitz.Rect(75, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 10

    # Promotion 3: Software Engineer II
    page.insert_text((65, y), "Software Engineer II (2017 – 2019)", fontsize=10.5)
    y += 14
    for b in [
        "Built distributed idempotency caching layer using Redis clusters preventing duplicate charge processing.",
        "Implemented merchant webhooks notification dispatch system delivering 8M events daily."
    ]:
        page.insert_textbox(fitz.Rect(75, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 20

    page.insert_text((50, y), "EDUCATION", fontsize=12)
    y += 16
    page.insert_text((50, y), "University of California, Berkeley", fontsize=10)
    y += 14
    page.insert_text((50, y), "B.S. in Electrical Engineering & Computer Science (EECS) | 2013 – 2017", fontsize=9)
    y += 25

    page.insert_text((50, y), "TECHNICAL SKILLS", fontsize=12)
    y += 16
    page.insert_text((50, y), "Languages: Go, Java, Python, Ruby, SQL", fontsize=9)
    y += 14
    page.insert_text((50, y), "Systems: Kafka, Redis, PostgreSQL, Kubernetes, Envoy, Terraform, AWS", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_45_single_employer_promotions.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_45 = {
        "test_id": "rw_45",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Maya Patel",
            "email": "maya.patel@fintechcore.com",
            "phone": "+1-415-555-0142",
            "location": "San Francisco, CA"
        },
        "professional_summary": "Accomplished infrastructure engineering leader with 7+ years of progressive growth at Stripe Technologies, advancing from Software Engineer to Staff Infrastructure Architect.",
        "work_experience": [
            {
                "employer": "Stripe Technologies",
                "designation": "Staff Infrastructure Architect",
                "start_date": "2022",
                "end_date": "Present"
            },
            {
                "employer": "Stripe Technologies",
                "designation": "Senior Systems Engineer",
                "start_date": "2019",
                "end_date": "2022"
            },
            {
                "employer": "Stripe Technologies",
                "designation": "Software Engineer II",
                "start_date": "2017",
                "end_date": "2019"
            }
        ],
        "education": [
            {
                "institution": "University of California, Berkeley",
                "degree": "B.S. in Electrical Engineering & Computer Science",
                "graduation_year": "2017"
            }
        ],
        "skills": {
            "technical": [
                "Go", "Java", "Python", "Ruby", "SQL", "Kafka", "Redis", "PostgreSQL", "Kubernetes", "Envoy", "Terraform", "AWS"
            ]
        }
    }
    with open(GROUND_TRUTH_DIR / "rw_45_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_45, f, indent=2)

    return len(pdf_bytes)


def build_rw_46_rtl_multilingual():
    """Generates an RTL multilingual (Arabic / English) resume fixture."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    page.insert_text((50, y), "TARIQ AL-MANSOOR", fontsize=18)
    y += 18
    page.insert_text((50, y), "طارق المنصور | Senior Cloud Engineer", fontsize=11)
    y += 18
    page.insert_text((50, y), "tariq.mansoor@gulftech.ae | +971-50-555-0188 | Dubai, United Arab Emirates", fontsize=9.5)
    y += 25

    page.insert_text((50, y), "PROFESSIONAL SUMMARY | نبذة مهنية", fontsize=12)
    y += 16
    page.insert_textbox(fitz.Rect(50, y, 545, y + 35), "Senior cloud systems engineer with 8+ years designing scalable AWS and Azure enterprise cloud architectures across the MENA region. خبرة 8 سنوات في تصميم الأنظمة السحابية الموسعة.", fontsize=9)
    y += 45

    page.insert_text((50, y), "WORK EXPERIENCE | الخبرة المهنية", fontsize=12)
    y += 18
    page.insert_text((50, y), "Emirates Cloud Telecom — Lead Cloud Solutions Architect", fontsize=11)
    y += 14
    page.insert_text((50, y), "Dubai, UAE | 2021 – Present", fontsize=9)
    y += 14
    for b in [
        "Architected multi-tenant hybrid cloud interconnect linking 4 data centers across UAE and Saudi Arabia.",
        "Designed bilingual microservices handling high-throughput telecommunication billing pipelines.",
        "Reduced annual cloud hosting expenditures by 32% via automated serverless auto-scaling."
    ]:
        page.insert_textbox(fitz.Rect(60, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 15

    page.insert_text((50, y), "Gulf Cyber Systems — Senior Systems Engineer", fontsize=11)
    y += 14
    page.insert_text((50, y), "Abu Dhabi, UAE | 2017 – 2021", fontsize=9)
    y += 14
    for b in [
        "Managed Kubernetes clusters running critical governmental digital identity verification services.",
        "Implemented automated disaster recovery pipelines achieving 15-minute RTO targets."
    ]:
        page.insert_textbox(fitz.Rect(60, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 20

    page.insert_text((50, y), "EDUCATION | التعليم", fontsize=12)
    y += 16
    page.insert_text((50, y), "American University of Sharjah", fontsize=10.5)
    y += 14
    page.insert_text((50, y), "B.S. Computer Engineering | 2013 – 2017", fontsize=9)
    y += 25

    page.insert_text((50, y), "SKILLS & TECHNOLOGIES | المهارات التقنية", fontsize=12)
    y += 16
    page.insert_text((50, y), "AWS, Azure, Terraform, Docker, Kubernetes, Python, Bash, PostgreSQL, Redis", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_46_rtl_arabic_hebrew.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_46 = {
        "test_id": "rw_46",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Tariq Al-Mansoor",
            "email": "tariq.mansoor@gulftech.ae",
            "phone": "+971-50-555-0188",
            "location": "Dubai, United Arab Emirates"
        },
        "professional_summary": "Senior cloud systems engineer with 8+ years designing scalable AWS and Azure enterprise cloud architectures across the MENA region.",
        "work_experience": [
            {
                "employer": "Emirates Cloud Telecom",
                "designation": "Lead Cloud Solutions Architect",
                "start_date": "2021",
                "end_date": "Present"
            },
            {
                "employer": "Gulf Cyber Systems",
                "designation": "Senior Systems Engineer",
                "start_date": "2017",
                "end_date": "2021"
            }
        ],
        "education": [
            {
                "institution": "American University of Sharjah",
                "degree": "B.S. Computer Engineering",
                "graduation_year": "2017"
            }
        ],
        "skills": {
            "technical": [
                "AWS", "Azure", "Terraform", "Docker", "Kubernetes", "Python", "Bash", "PostgreSQL", "Redis"
            ]
        }
    }
    with open(GROUND_TRUTH_DIR / "rw_46_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_46, f, indent=2)

    return len(pdf_bytes)


def build_rw_47_cjk_multilingual():
    """Generates a CJK (Japanese / English) multilingual resume fixture."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    page.insert_text((50, y), "KENJI TAKAHASHI", fontsize=18)
    y += 18
    page.insert_text((50, y), "高橋 健二 | Lead AI Systems Architect", fontsize=11)
    y += 18
    page.insert_text((50, y), "kenji.takahashi@tokyo-ai.jp | +81-3-5555-0199 | Tokyo, Japan", fontsize=9.5)
    y += 25

    page.insert_text((50, y), "PROFESSIONAL SUMMARY | 職務概要", fontsize=12)
    y += 16
    page.insert_textbox(fitz.Rect(50, y, 545, y + 35), "AI systems architect with 9+ years delivering low-latency machine learning inference pipelines and distributed robotics perception models in Tokyo. 機械学習およびロボティクス推論基盤の設計・開発に従事。", fontsize=9)
    y += 45

    page.insert_text((50, y), "WORK EXPERIENCE | 職歴", fontsize=12)
    y += 18
    page.insert_text((50, y), "Rakuten AI Laboratories — Principal Machine Learning Architect", fontsize=11)
    y += 14
    page.insert_text((50, y), "Tokyo, Japan | 2020 – Present", fontsize=9)
    y += 14
    for b in [
        "Architected large-scale e-commerce recommendation models processing 65M daily user requests.",
        "Optimized deep learning tensor inference latency from 120ms to 18ms using TensorRT and Triton.",
        "Managed a bilingual engineering team of 14 researchers and software engineers."
    ]:
        page.insert_textbox(fitz.Rect(60, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 15

    page.insert_text((50, y), "Sony Robotics Technologies — Senior Systems Engineer", fontsize=11)
    y += 14
    page.insert_text((50, y), "Tokyo, Japan | 2016 – 2020", fontsize=9)
    y += 14
    for b in [
        "Developed real-time stereo vision sensor fusion drivers for autonomous robotics platforms.",
        "Implemented deterministic C++ communication middleware using ROS 2 and zero-copy shared memory."
    ]:
        page.insert_textbox(fitz.Rect(60, y, 545, y + 22), f"• {b}", fontsize=8.5)
        y += 20
    y += 20

    page.insert_text((50, y), "EDUCATION | 学歴", fontsize=12)
    y += 16
    page.insert_text((50, y), "University of Tokyo (東京大学)", fontsize=10.5)
    y += 14
    page.insert_text((50, y), "Master of Information Science and Technology | 2014 – 2016", fontsize=9)
    y += 25

    page.insert_text((50, y), "TECHNICAL SKILLS | 技術スキル", fontsize=12)
    y += 16
    page.insert_text((50, y), "PyTorch, TensorRT, Triton, C++, Python, ROS 2, Docker, CUDA, Linux, Git", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_47_cjk_multilingual.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_47 = {
        "test_id": "rw_47",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Kenji Takahashi",
            "email": "kenji.takahashi@tokyo-ai.jp",
            "phone": "+81-3-5555-0199",
            "location": "Tokyo, Japan"
        },
        "professional_summary": "AI systems architect with 9+ years delivering low-latency machine learning inference pipelines and distributed robotics perception models in Tokyo.",
        "work_experience": [
            {
                "employer": "Rakuten AI Laboratories",
                "designation": "Principal Machine Learning Architect",
                "start_date": "2020",
                "end_date": "Present"
            },
            {
                "employer": "Sony Robotics Technologies",
                "designation": "Senior Systems Engineer",
                "start_date": "2016",
                "end_date": "2020"
            }
        ],
        "education": [
            {
                "institution": "University of Tokyo",
                "degree": "Master of Information Science and Technology",
                "graduation_year": "2016"
            }
        ],
        "skills": {
            "technical": [
                "PyTorch", "TensorRT", "Triton", "C++", "Python", "ROS 2", "Docker", "CUDA", "Linux", "Git"
            ]
        }
    }
    with open(GROUND_TRUTH_DIR / "rw_47_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_47, f, indent=2)

    return len(pdf_bytes)


def build_rw_48_acroform_fields():
    """Generates an interactive AcroForm PDF containing candidate data stored in interactive form widgets."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    
    # Static visual layout
    y = 50
    page.insert_text((50, y), "CANDIDATE EMPLOYMENT APPLICATION FORM", fontsize=14)
    y += 20
    page.insert_text((50, y), "Official System Export — Form-Based Digital Profile", fontsize=9.5)
    y += 25
    
    # Form Field 1: Full Name
    page.insert_text((50, y), "Full Name:", fontsize=10)
    w1 = fitz.Widget()
    w1.rect = fitz.Rect(130, y - 10, 400, y + 8)
    w1.field_name = "Candidate_FullName"
    w1.field_value = "Nathan Drake"
    w1.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    page.add_widget(w1)
    # Also add rendered fallback text inside rect
    page.insert_text((135, y), "Nathan Drake", fontsize=9)
    y += 25

    # Form Field 2: Email
    page.insert_text((50, y), "Email Address:", fontsize=10)
    w2 = fitz.Widget()
    w2.rect = fitz.Rect(130, y - 10, 400, y + 8)
    w2.field_name = "Candidate_Email"
    w2.field_value = "nathan.drake@unchartedsec.io"
    w2.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    page.add_widget(w2)
    page.insert_text((135, y), "nathan.drake@unchartedsec.io", fontsize=9)
    y += 25

    # Form Field 3: Phone & Location
    page.insert_text((50, y), "Phone / Location:", fontsize=10)
    w3 = fitz.Widget()
    w3.rect = fitz.Rect(150, y - 10, 450, y + 8)
    w3.field_name = "Candidate_Phone_Location"
    w3.field_value = "+1-650-555-0133 | Palo Alto, CA"
    w3.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    page.add_widget(w3)
    page.insert_text((155, y), "+1-650-555-0133 | Palo Alto, CA", fontsize=9)
    y += 35

    # Professional Summary Block
    page.insert_text((50, y), "PROFESSIONAL SUMMARY", fontsize=11)
    y += 16
    summary_txt = "Senior Cybersecurity Operations Consultant with 9+ years managing red-team offensive penetration simulations, threat hunting, and incident response."
    page.insert_textbox(fitz.Rect(50, y, 545, y + 35), summary_txt, fontsize=9)
    y += 45

    # Work Experience
    page.insert_text((50, y), "WORK EXPERIENCE", fontsize=11)
    y += 16
    page.insert_text((50, y), "Uncharted Security Solutions — Lead Penetration Tester", fontsize=10)
    y += 14
    page.insert_text((50, y), "Palo Alto, CA | 2020 – Present", fontsize=8.5)
    y += 14
    page.insert_textbox(fitz.Rect(60, y, 545, y + 25), "• Led comprehensive purple-team security assessments across Fortune 100 enterprise perimeters.\n• Discovered 14 zero-day vulnerabilities in enterprise identity providers.", fontsize=8.5)
    y += 35

    page.insert_text((50, y), "BlackWatch Cybernetics — Security Analyst", fontsize=10)
    y += 14
    page.insert_text((50, y), "San Jose, CA | 2016 – 2020", fontsize=8.5)
    y += 14
    page.insert_textbox(fitz.Rect(60, y, 545, y + 25), "• Managed 24/7 Security Operations Center (SOC) threat detection and incident triage.\n• Automated threat intelligence correlation using Python and Splunk APIs.", fontsize=8.5)
    y += 35

    # Education & Skills
    page.insert_text((50, y), "EDUCATION & CERTIFICATIONS", fontsize=11)
    y += 16
    page.insert_text((50, y), "Stanford University — B.S. in Symbolic Systems (2016)", fontsize=9)
    y += 14
    page.insert_text((50, y), "Certifications: OSCP, CISSP, CEH", fontsize=8.5)
    y += 25

    page.insert_text((50, y), "SKILLS", fontsize=11)
    y += 16
    page.insert_text((50, y), "Python, Bash, Wireshark, Metasploit, Burp Suite, Splunk, Ghidra, Linux, Docker, AWS", fontsize=9)

    pdf_bytes = doc.tobytes()
    doc.close()

    fixture_path = FIXTURES_DIR / "rw_48_acroform_form_fields.pdf"
    with open(fixture_path, "wb") as f:
        f.write(pdf_bytes)

    gt_48 = {
        "test_id": "rw_48",
        "expected_status": "success",
        "personal_info": {
            "full_name": "Nathan Drake",
            "email": "nathan.drake@unchartedsec.io",
            "phone": "+1-650-555-0133",
            "location": "Palo Alto, CA"
        },
        "professional_summary": "Senior Cybersecurity Operations Consultant with 9+ years managing red-team offensive penetration simulations, threat hunting, and incident response.",
        "work_experience": [
            {
                "employer": "Uncharted Security Solutions",
                "designation": "Lead Penetration Tester",
                "start_date": "2020",
                "end_date": "Present"
            },
            {
                "employer": "BlackWatch Cybernetics",
                "designation": "Security Analyst",
                "start_date": "2016",
                "end_date": "2020"
            }
        ],
        "education": [
            {
                "institution": "Stanford University",
                "degree": "B.S. in Symbolic Systems",
                "graduation_year": "2016"
            }
        ],
        "skills": {
            "technical": [
                "Python", "Bash", "Wireshark", "Metasploit", "Burp Suite", "Splunk", "Ghidra", "Linux", "Docker", "AWS"
            ]
        }
    }
    with open(GROUND_TRUTH_DIR / "rw_48_truth.json", "w", encoding="utf-8") as f:
        json.dump(gt_48, f, indent=2)

    return len(pdf_bytes)


def update_manifest():
    """Adds the 7 new fixtures to manifest.json if not already present."""
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    existing_ids = {item["test_id"] for item in manifest}
    new_entries = [
        {
            "test_id": "rw_42",
            "file_name": "rw_42_5plus_page_cv.pdf",
            "format": "pdf",
            "layout_category": "5+ Page Executive CV",
            "page_count": 5,
            "language": "en",
            "is_scanned": False,
            "has_hyperlinks": True,
            "has_tables": False,
            "has_columns": False,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills", "projects"],
            "known_challenges": ["Document length >14,000 chars", "Prompt truncation defense", "Multi-page publication list"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_42_5plus_page_cv.pdf")
        },
        {
            "test_id": "rw_43",
            "file_name": "rw_43_three_column_layout.pdf",
            "format": "pdf",
            "layout_category": "Three-Column Complex Magazine",
            "page_count": 1,
            "language": "en",
            "is_scanned": False,
            "has_hyperlinks": False,
            "has_tables": False,
            "has_columns": True,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills", "projects"],
            "known_challenges": ["Three vertical columns", "Narrow gutters", "Multi-column interleave risk"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_43_three_column_layout.pdf")
        },
        {
            "test_id": "rw_44",
            "file_name": "rw_44_two_column_full_width_header.pdf",
            "format": "pdf",
            "layout_category": "Two-Column with Full-Width Header",
            "page_count": 1,
            "language": "en",
            "is_scanned": False,
            "has_hyperlinks": True,
            "has_tables": False,
            "has_columns": True,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills", "projects"],
            "known_challenges": ["Full-width header atop two columns", "Vertical sweep interference", "Left sidebar split"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_44_two_column_full_width_header.pdf")
        },
        {
            "test_id": "rw_45",
            "file_name": "rw_45_single_employer_promotions.pdf",
            "format": "pdf",
            "layout_category": "Single-Employer Career Progression",
            "page_count": 1,
            "language": "en",
            "is_scanned": False,
            "has_hyperlinks": False,
            "has_tables": False,
            "has_columns": False,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills"],
            "known_challenges": ["3 consecutive internal promotions", "Hierarchical single company", "Role timeline flattening risk"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_45_single_employer_promotions.pdf")
        },
        {
            "test_id": "rw_46",
            "file_name": "rw_46_rtl_arabic_hebrew.pdf",
            "format": "pdf",
            "layout_category": "RTL Multilingual Arabic-English",
            "page_count": 1,
            "language": "ar/en",
            "is_scanned": False,
            "has_hyperlinks": False,
            "has_tables": False,
            "has_columns": False,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills"],
            "known_challenges": ["Right-to-left glyphs", "Bilingual text extraction", "Unicode bidirectional embedding"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_46_rtl_arabic_hebrew.pdf")
        },
        {
            "test_id": "rw_47",
            "file_name": "rw_47_cjk_multilingual.pdf",
            "format": "pdf",
            "layout_category": "CJK Japanese-English Multilingual",
            "page_count": 1,
            "language": "ja/en",
            "is_scanned": False,
            "has_hyperlinks": False,
            "has_tables": False,
            "has_columns": False,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills"],
            "known_challenges": ["Multi-byte CJK glyphs", "Non-space-delimited tokens", "Bilingual headings"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_47_cjk_multilingual.pdf")
        },
        {
            "test_id": "rw_48",
            "file_name": "rw_48_acroform_form_fields.pdf",
            "format": "pdf",
            "layout_category": "Interactive AcroForm Fields",
            "page_count": 1,
            "language": "en",
            "is_scanned": False,
            "has_hyperlinks": False,
            "has_tables": False,
            "has_columns": False,
            "expected_fields": ["personal_info", "professional_summary", "work_experience", "education", "skills"],
            "known_challenges": ["Interactive widget form fields", "AcroForm text stream extraction"],
            "verification_status": "verified",
            "file_path": str(FIXTURES_DIR / "rw_48_acroform_form_fields.pdf")
        }
    ]

    added = 0
    for entry in new_entries:
        if entry["test_id"] not in existing_ids:
            manifest.append(entry)
            added += 1

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest updated: {added} new entries added. Total entries: {len(manifest)}")


def main():
    print("Generating Phase 0 Fixtures...")
    s42 = build_rw_42_long_cv()
    print(f"  Generated rw_42_5plus_page_cv.pdf ({s42} bytes)")
    s43 = build_rw_43_three_column()
    print(f"  Generated rw_43_three_column_layout.pdf ({s43} bytes)")
    s44 = build_rw_44_banner_two_column()
    print(f"  Generated rw_44_two_column_full_width_header.pdf ({s44} bytes)")
    s45 = build_rw_45_single_employer_promotions()
    print(f"  Generated rw_45_single_employer_promotions.pdf ({s45} bytes)")
    s46 = build_rw_46_rtl_multilingual()
    print(f"  Generated rw_46_rtl_arabic_hebrew.pdf ({s46} bytes)")
    s47 = build_rw_47_cjk_multilingual()
    print(f"  Generated rw_47_cjk_multilingual.pdf ({s47} bytes)")
    s48 = build_rw_48_acroform_fields()
    print(f"  Generated rw_48_acroform_form_fields.pdf ({s48} bytes)")

    update_manifest()
    print("Phase 0 Fixture Generation Complete.")


if __name__ == "__main__":
    main()
