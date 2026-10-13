"""Normalized database storage and One-Resume-One-Row Excel/CSV export pipeline.

Processes extraction JSON results, manages SQLite persistence with relational
tables (education, experience, projects, certificates, skills, awards, etc.),
and generates:
  - resumes_one_row_per_candidate.xlsx
  - resumes_one_row_per_candidate.csv

Ensures:
  1. Exactly one export row per unique resume (deduplicating by content SHA-256).
  2. Multiple entries formatted within single cells using readable line breaks.
  3. Combined Certifications + Training + Courses into the 'Certificates' column,
     while preserving item type in canonical JSON/database.
  4. Preserves missing values as empty cells.
  5. 100% equivalence between CSV and Excel.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


EXPORT_COLUMNS = [
    "Resume_ID",
    "Candidate_Name",
    "Email",
    "Phone",
    "Location",
    "LinkedIn",
    "GitHub",
    "Portfolio",
    "Summary",
    "Skills",
    "Education",
    "Experience",
    "Projects",
    "Certificates",
    "Achievements",
    "Languages",
    "Publications",
    "Other_Details",
    "Source_File",
    "Extraction_Status",
]


def extract_val(item: Any) -> Any:
    """Unpack {'value': ..., 'source_line_ids': ...} wrapper or return item directly."""
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


def format_skills(skills_data: List[Dict[str, Any]]) -> str:
    """Format skills keeping groups or items separated by newlines."""
    if not skills_data:
        return ""
    groups = []
    for g in skills_data:
        category = g.get("category")
        items = g.get("items", [])
        if not items:
            continue
        items_str = ", ".join(items)
        if category:
            groups.append(f"{category}: {items_str}")
        else:
            groups.append(items_str)
    return "\n".join(groups)


def format_education(education_data: List[Dict[str, Any]]) -> str:
    """Format multiple education records into a clean multi-line block."""
    if not education_data:
        return ""
    entries = []
    for edu in education_data:
        degree = extract_val(edu.get("degree")) or ""
        inst = extract_val(edu.get("institution")) or ""
        loc = extract_val(edu.get("location")) or ""
        dates = extract_val(edu.get("dates")) or {}
        grad = extract_val(edu.get("graduation")) or ""
        gpa = extract_val(edu.get("gpa")) or {}

        header_parts = [part for part in [degree, inst] if part]
        header = " - ".join(header_parts) if header_parts else "Degree"

        details = []
        if isinstance(dates, dict) and (dates.get("start") or dates.get("end")):
            d_str = f"Dates: {dates.get('start', '')} – {dates.get('end', '')}".strip()
            details.append(d_str)
        elif grad:
            details.append(f"Graduation: {grad}")

        if loc:
            details.append(f"Location: {loc}")

        if isinstance(gpa, dict) and gpa.get("score"):
            score = gpa.get("score")
            scale = gpa.get("scale")
            details.append(f"GPA: {score}/{scale}" if scale else f"GPA: {score}")

        entry_lines = [header]
        if details:
            entry_lines.append(" | ".join(details))
        entries.append("\n".join(entry_lines))

    return "\n\n".join(entries)


def format_experience(experience_data: List[Dict[str, Any]]) -> str:
    """Format multiple job records with title, company, dates, bullets."""
    if not experience_data:
        return ""
    entries = []
    for exp in experience_data:
        title = extract_val(exp.get("title")) or ""
        company = extract_val(exp.get("company")) or ""
        loc = extract_val(exp.get("location")) or ""
        dates = extract_val(exp.get("dates")) or {}

        header_parts = [part for part in [title, company] if part]
        header = " at ".join(header_parts) if len(header_parts) == 2 else (header_parts[0] if header_parts else "Experience")

        meta = []
        if isinstance(dates, dict) and (dates.get("start") or dates.get("end")):
            meta.append(f"{dates.get('start', '')} – {dates.get('end', '')}")
        if loc:
            meta.append(loc)

        lines = [header]
        if meta:
            lines.append(" | ".join(meta))

        bullets = exp.get("bullets", [])
        for b in bullets:
            clean_b = re.sub(r"^[•–−*-]\s*", "", b.strip())
            if clean_b:
                lines.append(f"• {clean_b}")

        entries.append("\n".join(lines))

    return "\n\n".join(entries)


def format_projects(projects_data: List[Dict[str, Any]]) -> str:
    """Format multiple project records with name, dates, tech stack, bullets."""
    if not projects_data:
        return ""
    entries = []
    for prj in projects_data:
        name = extract_val(prj.get("name")) or ""
        name = re.sub(r"^[•–−*-]\s*", "", name).rstrip(":")
        dates = extract_val(prj.get("dates")) or {}
        techs = [extract_val(t) for t in prj.get("technologies", []) if extract_val(t)]

        header = name if name else "Project"
        meta = []
        if isinstance(dates, dict) and (dates.get("start") or dates.get("end")):
            meta.append(f"{dates.get('start', '')} – {dates.get('end', '')}")
        if techs:
            meta.append(f"Technologies: {', '.join(techs)}")

        lines = [header]
        if meta:
            lines.append(" | ".join(meta))

        bullets = prj.get("bullets", [])
        if bullets:
            for b in bullets:
                clean_b = re.sub(r"^[•–−*-]\s*", "", b.strip())
                if clean_b:
                    lines.append(f"• {clean_b}")
        else:
            desc = prj.get("description", "")
            if desc:
                # remove duplicated Tech: prefix if already present
                lines.append(desc.strip())

        entries.append("\n".join(lines))

    return "\n\n".join(entries)


def classify_cert_type(name: str, details: str = "") -> str:
    """Classify credential item type: Certification, Course, Training, or License."""
    comb = f"{name} {details}".lower()
    if any(k in comb for k in ["course", "coursera", "udemy", "edx"]):
        return "Course"
    if any(k in comb for k in ["training", "bootcamp", "workshop", "trained"]):
        return "Training"
    if any(k in comb for k in ["license", "cpa", "cfa", "board"]):
        return "License"
    return "Certification"


def format_certificates(certifications_data: List[Dict[str, Any]]) -> str:
    """Combine training, certifications, and courses into a unified Certificates cell."""
    if not certifications_data:
        return ""
    entries = []
    for cert in certifications_data:
        name = extract_val(cert.get("name")) or ""
        name = re.sub(r"^[•–−*-]\s*", "", name).strip()
        details = cert.get("details", "") or ""
        details = details.strip()

        ctype = cert.get("item_type") or classify_cert_type(name, details)
        prefix = f"[{ctype}] {name}" if name else f"[{ctype}]"

        if details:
            entries.append(f"{prefix}\nDetails: {details}")
        else:
            entries.append(prefix)

    return "\n\n".join(entries)


def parse_resume_to_row(data: Dict[str, Any], default_id: str = "") -> Dict[str, Any]:
    """Extract canonical structured data from full resume.json into an export row."""
    st = data.get("structured", {})
    src = data.get("source", {})
    contact = st.get("contact", {})

    # Name
    cand_name = extract_val(contact.get("name")) or ""

    # Emails
    emails = [extract_val(e) for e in contact.get("emails", []) if extract_val(e)]
    email_str = "\n".join(emails)

    # Phones
    phones = [extract_val(p) for p in contact.get("phones", []) if extract_val(p)]
    phone_str = "\n".join(phones)

    # Locations
    locs = [extract_val(l) for l in contact.get("locations", []) if extract_val(l)]
    loc_str = "\n".join(locs)

    # Categorize Links
    all_links = [extract_val(l) for l in contact.get("links", []) if extract_val(l)]
    li_links, gh_links, port_links = [], [], []
    for l in all_links:
        ll = l.lower()
        if "linkedin" in ll:
            li_links.append(l)
        elif "github" in ll:
            gh_links.append(l)
        else:
            port_links.append(l)

    # Summary
    summary_parts = []
    for s in st.get("summary", []):
        sv = extract_val(s)
        if sv:
            summary_parts.append(sv.strip())
    summary_str = "\n\n".join(summary_parts)

    # Sections
    skills_str = format_skills(st.get("skills", []))
    edu_str = format_education(st.get("education", []))
    exp_str = format_experience(st.get("experience", []))
    prj_str = format_projects(st.get("projects", []))
    cert_str = format_certificates(st.get("certifications", []))

    # Other Sections (Awards, Metrics, Publications)
    awards_parts = []
    pub_parts = []
    metric_parts = []
    other_parts = []
    for sec in st.get("other_sections", []):
        canon = sec.get("canonical", "")
        txt = sec.get("text", "")
        clean_txt = "\n".join(re.sub(r"^[•–−*-]\s*", "• ", line).strip() for line in txt.splitlines() if line.strip())
        if canon == "awards":
            awards_parts.append(clean_txt)
        elif canon == "publications":
            pub_parts.append(clean_txt)
        elif canon == "metrics":
            metric_parts.append(f"Key Metrics:\n{clean_txt}")
        else:
            hd = sec.get("original_heading") or canon
            other_parts.append(f"[{hd}]\n{clean_txt}")

    achievements_str = "\n\n".join(awards_parts)
    publications_str = "\n\n".join(pub_parts)

    other_combined = [p for p in (metric_parts + other_parts) if p]
    other_str = "\n\n".join(other_combined)

    # Languages
    lang_str = ""

    # Traceability
    src_file = src.get("filename", "")
    comp_status = data.get("quality", {}).get("completeness", {}).get("status", "pass")
    schema_errs = data.get("quality", {}).get("schema_errors", [])
    status = "Verified Pass" if (comp_status == "pass" and not schema_errs) else ("Review Needed" if comp_status == "pass" else f"Completeness {comp_status}")

    return {
        "Resume_ID": default_id,
        "Candidate_Name": cand_name,
        "Email": email_str,
        "Phone": phone_str,
        "Location": loc_str,
        "LinkedIn": "\n".join(li_links),
        "GitHub": "\n".join(gh_links),
        "Portfolio": "\n".join(port_links),
        "Summary": summary_str,
        "Skills": skills_str,
        "Education": edu_str,
        "Experience": exp_str,
        "Projects": prj_str,
        "Certificates": cert_str,
        "Achievements": achievements_str,
        "Languages": lang_str,
        "Publications": publications_str,
        "Other_Details": other_str,
        "Source_File": src_file,
        "Extraction_Status": status,
        "sha256": src.get("sha256", ""),
        "duplicate_of": src.get("duplicate_of"),
    }


def init_export_database(conn: sqlite3.Connection) -> None:
    """Initialize relational schema for normalized resumes and entity storage."""
    conn.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS candidates (
        resume_id TEXT PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        candidate_name TEXT,
        email TEXT,
        phone TEXT,
        location TEXT,
        linkedin TEXT,
        github TEXT,
        portfolio TEXT,
        summary TEXT,
        languages TEXT,
        source_file TEXT NOT NULL,
        extraction_status TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS candidate_education (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        degree TEXT,
        institution TEXT,
        location TEXT,
        start_date TEXT,
        end_date TEXT,
        graduation TEXT,
        gpa TEXT
    );

    CREATE TABLE IF NOT EXISTS candidate_experience (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        title TEXT,
        company TEXT,
        location TEXT,
        start_date TEXT,
        end_date TEXT,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS candidate_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        name TEXT,
        start_date TEXT,
        end_date TEXT,
        technologies TEXT,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS candidate_certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        name TEXT,
        details TEXT
    );

    CREATE TABLE IF NOT EXISTS candidate_skills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        category TEXT,
        skills_text TEXT
    );

    CREATE TABLE IF NOT EXISTS candidate_achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resume_id TEXT NOT NULL REFERENCES candidates(resume_id),
        ordinal INTEGER NOT NULL,
        canonical TEXT,
        heading TEXT,
        content TEXT
    );
    """)


def save_candidate_to_database(conn: sqlite3.Connection, resume_id: str, data: Dict[str, Any], row: Dict[str, Any]) -> None:
    """Save normalized relational records for one candidate."""
    st = data.get("structured", {})
    with conn:
        conn.execute("""
        INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(resume_id) DO UPDATE SET
            candidate_name=excluded.candidate_name,
            email=excluded.email,
            phone=excluded.phone,
            location=excluded.location,
            linkedin=excluded.linkedin,
            github=excluded.github,
            portfolio=excluded.portfolio,
            summary=excluded.summary,
            languages=excluded.languages,
            source_file=excluded.source_file,
            extraction_status=excluded.extraction_status
        """, (
            resume_id,
            row["sha256"],
            row["Candidate_Name"],
            row["Email"],
            row["Phone"],
            row["Location"],
            row["LinkedIn"],
            row["GitHub"],
            row["Portfolio"],
            row["Summary"],
            row["Languages"],
            row["Source_File"],
            row["Extraction_Status"]
        ))

        # Delete existing child rows for clean update
        for tbl in ["candidate_education", "candidate_experience", "candidate_projects",
                    "candidate_certificates", "candidate_skills", "candidate_achievements"]:
            conn.execute(f"DELETE FROM {tbl} WHERE resume_id=?", (resume_id,))

        # Education
        for i, edu in enumerate(st.get("education", [])):
            deg = extract_val(edu.get("degree"))
            inst = extract_val(edu.get("institution"))
            loc = extract_val(edu.get("location"))
            dates = extract_val(edu.get("dates")) or {}
            grad = extract_val(edu.get("graduation"))
            gpa = extract_val(edu.get("gpa")) or {}
            gpa_str = f"{gpa.get('score')}/{gpa.get('scale')}" if gpa.get("scale") else gpa.get("score")
            conn.execute("""
            INSERT INTO candidate_education (resume_id, ordinal, degree, institution, location, start_date, end_date, graduation, gpa)
            VALUES (?,?,?,?,?,?,?,?,?)
            """, (resume_id, i, deg, inst, loc, dates.get("start"), dates.get("end"), grad, gpa_str))

        # Experience
        for i, exp in enumerate(st.get("experience", [])):
            t = extract_val(exp.get("title"))
            c = extract_val(exp.get("company"))
            loc = extract_val(exp.get("location"))
            dates = extract_val(exp.get("dates")) or {}
            desc = "\n".join([f"• {re.sub(r'^[•–−*-]\s*', '', b.strip())}" for b in exp.get("bullets", [])])
            conn.execute("""
            INSERT INTO candidate_experience (resume_id, ordinal, title, company, location, start_date, end_date, description)
            VALUES (?,?,?,?,?,?,?,?)
            """, (resume_id, i, t, c, loc, dates.get("start"), dates.get("end"), desc))

        # Projects
        for i, prj in enumerate(st.get("projects", [])):
            n = extract_val(prj.get("name"))
            dates = extract_val(prj.get("dates")) or {}
            techs = ", ".join([extract_val(t) for t in prj.get("technologies", []) if extract_val(t)])
            bullets = [f"• {re.sub(r'^[•–−*-]\s*', '', b.strip())}" for b in prj.get("bullets", [])]
            desc = "\n".join(bullets) if bullets else prj.get("description", "")
            conn.execute("""
            INSERT INTO candidate_projects (resume_id, ordinal, name, start_date, end_date, technologies, description)
            VALUES (?,?,?,?,?,?,?)
            """, (resume_id, i, n, dates.get("start"), dates.get("end"), techs, desc))

        # Certificates & Training
        for i, cert in enumerate(st.get("certifications", [])):
            name = extract_val(cert.get("name")) or ""
            name = re.sub(r"^[•–−*-]\s*", "", name).strip()
            details = cert.get("details", "") or ""
            ctype = cert.get("item_type") or classify_cert_type(name, details)
            conn.execute("""
            INSERT INTO candidate_certificates (resume_id, ordinal, item_type, name, details)
            VALUES (?,?,?,?,?)
            """, (resume_id, i, ctype, name, details))

        # Skills
        for i, sk in enumerate(st.get("skills", [])):
            cat = sk.get("category")
            items = ", ".join(sk.get("items", []))
            conn.execute("""
            INSERT INTO candidate_skills (resume_id, ordinal, category, skills_text)
            VALUES (?,?,?,?)
            """, (resume_id, i, cat, items))

        # Other Sections / Achievements
        for i, sec in enumerate(st.get("other_sections", [])):
            canon = sec.get("canonical", "")
            hd = sec.get("original_heading") or canon
            txt = sec.get("text", "")
            conn.execute("""
            INSERT INTO candidate_achievements (resume_id, ordinal, canonical, heading, content)
            VALUES (?,?,?,?,?)
            """, (resume_id, i, canon, hd, txt))


def write_csv_export(rows: List[Dict[str, Any]], destination: Path) -> None:
    """Export one resume per row to CSV using UTF-8-SIG for universal Excel compatibility."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (r.get(k) or "") for k in EXPORT_COLUMNS})


def write_excel_export(rows: List[Dict[str, Any]], destination: Path) -> None:
    """Export one resume per row to formatted Excel workbook (.xlsx)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Candidates"

    # Styling definitions
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell_font = Font(name="Calibri", size=10)
    border_thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    # Write Header
    for col_idx, col_name in enumerate(EXPORT_COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border_thin

    ws.row_dimensions[1].height = 28

    # Write Rows
    for row_idx, r in enumerate(rows, 2):
        for col_idx, col_name in enumerate(EXPORT_COLUMNS, 1):
            val = r.get(col_name) or ""
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = cell_font
            cell.border = border_thin
            align_h = "center" if col_name in ("Resume_ID", "Extraction_Status") else "left"
            cell.alignment = Alignment(horizontal=align_h, vertical="top", wrap_text=True)

    # Set column widths
    width_map = {
        "Resume_ID": 14,
        "Candidate_Name": 24,
        "Email": 30,
        "Phone": 18,
        "Location": 22,
        "LinkedIn": 32,
        "GitHub": 28,
        "Portfolio": 30,
        "Summary": 45,
        "Skills": 40,
        "Education": 45,
        "Experience": 55,
        "Projects": 50,
        "Certificates": 45,
        "Achievements": 40,
        "Languages": 20,
        "Publications": 45,
        "Other_Details": 35,
        "Source_File": 32,
        "Extraction_Status": 18,
    }

    for col_idx, col_name in enumerate(EXPORT_COLUMNS, 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width_map.get(col_name, 25)

    ws.freeze_panes = "B2"
    wb.save(destination)


def process_and_export(
    input_dirs: List[Path],
    output_dir: Path,
    db_path: Optional[Path] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Process all resume extraction results, deduplicate by content, save to DB, and export."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if db_path:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        init_export_database(conn)
    else:
        conn = None

    seen_digests: Dict[str, str] = {}
    unique_rows: List[Dict[str, Any]] = []
    total_processed = 0
    duplicate_count = 0

    all_resumes: List[Tuple[str, Path, Dict[str, Any]]] = []

    for d in input_dirs:
        for json_path in sorted(d.glob("*/resume.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                folder_name = json_path.parent.name
                all_resumes.append((folder_name, json_path, data))
            except Exception:
                continue

    # Sort so R01..R20 order is prioritized over hash keys
    all_resumes.sort(key=lambda x: (0 if re.match(r"^R\d+$", x[0]) else 1, x[0]))

    for folder_name, json_path, data in all_resumes:
        total_processed += 1
        row = parse_resume_to_row(data, default_id=folder_name)
        sha = row["sha256"]

        if sha in seen_digests:
            duplicate_count += 1
            continue

        seen_digests[sha] = row["Resume_ID"]
        unique_rows.append(row)

        if conn:
            save_candidate_to_database(conn, row["Resume_ID"], data, row)

    if conn:
        conn.close()

    # Generate CSV & Excel
    csv_file = output_dir / "resumes_one_row_per_candidate.csv"
    xlsx_file = output_dir / "resumes_one_row_per_candidate.xlsx"

    write_csv_export(unique_rows, csv_file)
    write_excel_export(unique_rows, xlsx_file)

    stats = {
        "total_files_examined": total_processed,
        "unique_resumes": len(unique_rows),
        "duplicates_skipped": duplicate_count,
        "csv_path": str(csv_file),
        "xlsx_path": str(xlsx_file),
    }

    return unique_rows, stats


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Export one resume per row to Excel and CSV")
    parser.add_argument("inputs", nargs="+", type=Path, help="Directories containing resume.json results")
    parser.add_argument("--out", type=Path, default=Path("exported_results"), help="Output directory for Excel and CSV")
    parser.add_argument("--db", type=Path, default=Path("exported_results/resumes_relational.sqlite"), help="SQLite database path")
    args = parser.parse_args(argv)

    rows, stats = process_and_export(args.inputs, args.out, args.db)
    print(json.dumps(stats, indent=2))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
