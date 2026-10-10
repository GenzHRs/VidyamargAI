"""
Secure LaTeX Generation and Compilation Service.

Guarantees:
- Strict character escaping against LaTeX macro injection
- Disabled shell-escape (-no-shell-escape)
- Temporary sandboxed compilation with resource timeouts
- Path masking in compile errors
- Graceful degradation when pdflatex is not installed
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Any, Optional, Tuple, List
from app.services.project_normalizer import canonicalize_projects_list, clean_bullet_text

logger = logging.getLogger("app.latex_service")

# Maximum allowed LaTeX source size (1MB)
MAX_LATEX_SOURCE_SIZE = 1 * 1024 * 1024
# Maximum allowed compiled PDF size (20MB)
MAX_PDF_SIZE = 20 * 1024 * 1024
# Compilation timeout in seconds
COMPILATION_TIMEOUT_SECONDS = 15


_LATEX_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "<": r"$<$",
    ">": r"$>$",
}
_LATEX_PATTERN = re.compile(r"([\\&%$#_{}~^<>])")


def escape_latex(text: Any) -> str:
    """
    Escapes all LaTeX special characters in user text to prevent command injection
    or compilation syntax failures using a single-pass regex substitution.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Strip control characters except newline and tab
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")
    return _LATEX_PATTERN.sub(lambda m: _LATEX_MAP[m.group(1)], text)


def is_latex_installed() -> bool:
    """Returns True if pdflatex executable is found on system PATH."""
    return shutil.which("pdflatex") is not None


def render_resume_to_latex(data: Dict[str, Any], template_latex: str = "") -> str:
    """
    Renders structured resume JSON data into a valid Overleaf-compatible LaTeX document.
    All dynamic values are escaped via escape_latex.
    """
    if not template_latex:
        from app.services.resume_templates_data import RESUME_TEMPLATES
        template_latex = RESUME_TEMPLATES[0]["latex_template"]
    rendered = template_latex

    # 1. Personal Information
    personal = data.get("personal_info", {})
    full_name = escape_latex(personal.get("full_name", personal.get("name", "Candidate Name")))
    email = escape_latex(personal.get("email", ""))
    phone = escape_latex(personal.get("phone", ""))
    location = escape_latex(personal.get("location", personal.get("address", "")))

    # Links
    links_list = []
    if personal.get("linkedin"):
        links_list.append(r"\href{" + escape_latex(personal["linkedin"]) + "}{LinkedIn}")
    if personal.get("github"):
        links_list.append(r"\href{" + escape_latex(personal["github"]) + "}{GitHub}")
    if personal.get("portfolio"):
        links_list.append(r"\href{" + escape_latex(personal["portfolio"]) + "}{Portfolio}")
    for custom_link in personal.get("custom_links", []):
        if isinstance(custom_link, dict):
            links_list.append(r"\href{" + escape_latex(custom_link.get("url", "")) + "}{" + escape_latex(custom_link.get("label", "Link")) + "}")
        elif isinstance(custom_link, str):
            links_list.append(escape_latex(custom_link))

    links_str = " $\\mid$ ".join(links_list) if links_list else ""

    rendered = rendered.replace("<VAR:FULL_NAME>", full_name)
    rendered = rendered.replace("<VAR:EMAIL>", email)
    rendered = rendered.replace("<VAR:PHONE>", phone)
    rendered = rendered.replace("<VAR:LOCATION>", location)
    rendered = rendered.replace("<VAR:LINKS>", links_str)

    # 2. Summary Block
    summary_text = data.get("summary") or data.get("professional_summary") or data.get("career_objective", "")
    summary_pattern = re.compile(r"<BLOCK:SUMMARY>(.*?)</BLOCK:SUMMARY>", re.DOTALL)
    if summary_text:
        rendered = summary_pattern.sub(
            lambda m: m.group(1).replace("<VAR:SUMMARY_TEXT>", escape_latex(summary_text)),
            rendered
        )
    else:
        rendered = summary_pattern.sub("", rendered)

    # 3. Skills Loop
    skills_data = data.get("skills", {})
    skills_pattern = re.compile(r"<BLOCK:SKILLS>(.*?)</BLOCK:SKILLS>", re.DOTALL)
    if skills_data:
        # Handle dict categories or flat list
        categories: List[Tuple[str, str]] = []
        if isinstance(skills_data, dict):
            for cat_name, items in skills_data.items():
                if isinstance(items, list):
                    items_str = ", ".join([escape_latex(x) for x in items])
                else:
                    items_str = escape_latex(str(items))
                categories.append((escape_latex(cat_name), items_str))
        elif isinstance(skills_data, list):
            items_str = ", ".join([escape_latex(x) for x in skills_data])
            categories.append(("Technical Skills", items_str))

        def replace_skills(match):
            block_content = match.group(1)
            loop_pattern = re.compile(r"<LOOP:SKILLS_CATEGORIES>(.*?)</LOOP:SKILLS_CATEGORIES>", re.DOTALL)
            loop_match = loop_pattern.search(block_content)
            if not loop_match:
                return block_content
            loop_template = loop_match.group(1)
            expanded_items = []
            for cat_name, items_str in categories:
                item_rendered = loop_template.replace("<VAR:CATEGORY_NAME>", cat_name).replace("<VAR:CATEGORY_ITEMS>", items_str)
                expanded_items.append(item_rendered)
            return loop_pattern.sub(lambda _: "".join(expanded_items), block_content)

        rendered = skills_pattern.sub(replace_skills, rendered)
    else:
        rendered = skills_pattern.sub("", rendered)

    # 4. Work Experience Loop
    experience_list = data.get("experience", data.get("work_experience", []))
    exp_pattern = re.compile(r"<BLOCK:EXPERIENCE>(.*?)</BLOCK:EXPERIENCE>", re.DOTALL)
    if experience_list:
        def replace_experience(match):
            block_content = match.group(1)
            loop_pattern = re.compile(r"<LOOP:EXPERIENCE>(.*?)</LOOP:EXPERIENCE>", re.DOTALL)
            loop_match = loop_pattern.search(block_content)
            if not loop_match:
                return block_content
            loop_template = loop_match.group(1)
            expanded_entries = []
            for job in experience_list:
                job_rendered = loop_template
                job_rendered = job_rendered.replace("<VAR:JOB_TITLE>", escape_latex(job.get("title", job.get("role", ""))))
                job_rendered = job_rendered.replace("<VAR:JOB_COMPANY>", escape_latex(job.get("company", "")))
                job_rendered = job_rendered.replace("<VAR:JOB_LOCATION>", escape_latex(job.get("location", "")))
                dates = f"{job.get('start_date', '')} -- {job.get('end_date', 'Present')}".strip(" -")
                job_rendered = job_rendered.replace("<VAR:JOB_DATES>", escape_latex(dates))

                # Bullets inside job
                bullets_pattern = re.compile(r"<LOOP:JOB_BULLETS>(.*?)</LOOP:JOB_BULLETS>", re.DOTALL)
                bullets = job.get("bullets", job.get("responsibilities", job.get("highlights", [])))
                if isinstance(bullets, str):
                    bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
                if bullets:
                    b_match = bullets_pattern.search(job_rendered)
                    if b_match:
                        b_template = b_match.group(1)
                        bullets_expanded = "".join(b_template.replace("<VAR:BULLET_TEXT>", escape_latex(b)) for b in bullets)
                        job_rendered = bullets_pattern.sub(lambda _: bullets_expanded, job_rendered)
                else:
                    job_rendered = bullets_pattern.sub("", job_rendered)

                expanded_entries.append(job_rendered)
            return loop_pattern.sub(lambda _: "".join(expanded_entries), block_content)

        rendered = exp_pattern.sub(replace_experience, rendered)
    else:
        rendered = exp_pattern.sub("", rendered)

    # 5. Projects Loop
    projects_list = canonicalize_projects_list(data.get("projects", []))
    proj_pattern = re.compile(r"<BLOCK:PROJECTS>(.*?)</BLOCK:PROJECTS>", re.DOTALL)
    if projects_list:
        def replace_projects(match):
            block_content = match.group(1)
            loop_pattern = re.compile(r"<LOOP:PROJECTS>(.*?)</LOOP:PROJECTS>", re.DOTALL)
            loop_match = loop_pattern.search(block_content)
            if not loop_match:
                return block_content
            loop_template = loop_match.group(1)
            expanded = []
            for proj in projects_list:
                p_rendered = loop_template
                p_rendered = p_rendered.replace("<VAR:PROJECT_NAME>", escape_latex(proj.get("name", proj.get("title", ""))))
                p_rendered = p_rendered.replace("<VAR:PROJECT_TECH>", escape_latex(proj.get("tech_stack", proj.get("technologies", ""))))
                dates = f"{proj.get('start_date', '')} {proj.get('end_date', '')}".strip() or proj.get("dates", "")
                p_rendered = p_rendered.replace("<VAR:PROJECT_DATES>", escape_latex(dates))
                link_text = ""
                if proj.get("link") or proj.get("url"):
                    link_text = r"\href{" + escape_latex(proj.get("link") or proj.get("url")) + r"}{\small\texttt{Link}}"
                p_rendered = p_rendered.replace("<VAR:PROJECT_LINK>", link_text)

                bullets_pattern = re.compile(r"<LOOP:PROJECT_BULLETS>(.*?)</LOOP:PROJECT_BULLETS>", re.DOTALL)
                bullets = proj.get("bullets") or []
                if bullets:
                    b_match = bullets_pattern.search(p_rendered)
                    if b_match:
                        b_template = b_match.group(1)
                        bullets_expanded = "".join(b_template.replace("<VAR:BULLET_TEXT>", escape_latex(clean_bullet_text(str(b)))) for b in bullets if clean_bullet_text(str(b)))
                        p_rendered = bullets_pattern.sub(lambda _: bullets_expanded, p_rendered)
                else:
                    p_rendered = bullets_pattern.sub("", p_rendered)
                expanded.append(p_rendered)
            return loop_pattern.sub(lambda _: "".join(expanded), block_content)

        rendered = proj_pattern.sub(replace_projects, rendered)
    else:
        rendered = proj_pattern.sub("", rendered)

    # 6. Education Loop
    education_list = data.get("education", [])
    edu_pattern = re.compile(r"<BLOCK:EDUCATION>(.*?)</BLOCK:EDUCATION>", re.DOTALL)
    if education_list:
        def replace_education(match):
            block_content = match.group(1)
            loop_pattern = re.compile(r"<LOOP:EDUCATION>(.*?)</LOOP:EDUCATION>", re.DOTALL)
            loop_match = loop_pattern.search(block_content)
            if not loop_match:
                return block_content
            loop_template = loop_match.group(1)
            expanded = []
            for edu in education_list:
                e_rendered = loop_template
                e_rendered = e_rendered.replace("<VAR:DEGREE>", escape_latex(edu.get("degree", "")))
                e_rendered = e_rendered.replace("<VAR:INSTITUTION>", escape_latex(edu.get("institution", edu.get("university", ""))))
                e_rendered = e_rendered.replace("<VAR:EDU_LOCATION>", escape_latex(edu.get("location", "")))
                dates = f"{edu.get('start_date', '')} -- {edu.get('end_date', edu.get('graduation_year', ''))}".strip(" -")
                e_rendered = e_rendered.replace("<VAR:EDU_DATES>", escape_latex(dates))
                details = []
                if edu.get("gpa"):
                    details.append(f"GPA: {escape_latex(edu['gpa'])}")
                if edu.get("honors"):
                    details.append(escape_latex(edu["honors"]))
                e_rendered = e_rendered.replace("<VAR:EDU_DETAILS>", " $\\cdot$ ".join(details))
                expanded.append(e_rendered)
            return loop_pattern.sub(lambda _: "".join(expanded), block_content)

        rendered = edu_pattern.sub(replace_education, rendered)
    else:
        rendered = edu_pattern.sub("", rendered)

    # 7. Certifications Loop
    certs_list = data.get("certifications", [])
    cert_pattern = re.compile(r"<BLOCK:CERTIFICATIONS>(.*?)</BLOCK:CERTIFICATIONS>", re.DOTALL)
    if certs_list:
        def replace_certs(match):
            block_content = match.group(1)
            loop_pattern = re.compile(r"<LOOP:CERTIFICATIONS>(.*?)</LOOP:CERTIFICATIONS>", re.DOTALL)
            loop_match = loop_pattern.search(block_content)
            if not loop_match:
                return block_content
            loop_template = loop_match.group(1)
            expanded = []
            for cert in certs_list:
                c_rendered = loop_template
                if isinstance(cert, str):
                    c_rendered = c_rendered.replace("<VAR:CERT_NAME>", escape_latex(cert))
                    c_rendered = c_rendered.replace("<VAR:CERT_ISSUER>", "")
                    c_rendered = c_rendered.replace("<VAR:CERT_DATE>", "")
                elif isinstance(cert, dict):
                    c_rendered = c_rendered.replace("<VAR:CERT_NAME>", escape_latex(cert.get("name", "")))
                    c_rendered = c_rendered.replace("<VAR:CERT_ISSUER>", escape_latex(cert.get("issuer", "")))
                    c_rendered = c_rendered.replace("<VAR:CERT_DATE>", escape_latex(cert.get("date", "")))
                expanded.append(c_rendered)
            return loop_pattern.sub(lambda _: "".join(expanded), block_content)

        rendered = cert_pattern.sub(replace_certs, rendered)
    else:
        rendered = cert_pattern.sub("", rendered)

    # Clean up any leftover placeholder markers
    rendered = re.sub(r"<VAR:[A-Z_]+>", "", rendered)
    rendered = re.sub(r"</?BLOCK:[A-Z_]+>", "", rendered)
    rendered = re.sub(r"</?LOOP:[A-Z_]+>", "", rendered)

    return rendered


def compile_latex_to_pdf(
    latex_source: str,
    timeout: int = COMPILATION_TIMEOUT_SECONDS
) -> Tuple[bool, Optional[bytes], Optional[str]]:
    """
    Compiles LaTeX source to PDF safely.
    - Limits source size to MAX_LATEX_SOURCE_SIZE.
    - Runs in a clean temporary directory with -no-shell-escape.
    - Hides internal filesystem paths from errors.
    - If pdflatex is not installed, returns (False, None, error_message).
    """
    if len(latex_source.encode("utf-8")) > MAX_LATEX_SOURCE_SIZE:
        return False, None, "LaTeX source exceeds the 1MB safety size limit"

    if not is_latex_installed():
        return False, None, (
            "LaTeX compilation engine (pdflatex) is not installed on this server. "
            "You can download the generated Overleaf-compatible .tex source file directly "
            "to compile in Overleaf or configure TeX Live."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        tex_path = os.path.join(temp_dir, "resume.tex")
        pdf_path = os.path.join(temp_dir, "resume.pdf")

        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)

        cmd = [
            "pdflatex",
            "-no-shell-escape",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "resume.tex"
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                if file_size > MAX_PDF_SIZE:
                    return False, None, "Generated PDF exceeds the maximum size limit of 20MB"
                with open(pdf_path, "rb") as pf:
                    pdf_bytes = pf.read()
                return True, pdf_bytes, None

            # Compilation failed — sanitize error output by removing temp directory path
            output = result.stdout or result.stderr or "LaTeX compilation error occurred."
            sanitized_output = output.replace(temp_dir, "/sandbox")
            # Grab relevant error lines
            error_lines = [
                line for line in sanitized_output.split("\n")
                if line.startswith("!") or "error" in line.lower() or "fatal" in line.lower()
            ]
            summary_err = "\n".join(error_lines[:5]) if error_lines else "LaTeX syntax or package compilation failure."
            return False, None, summary_err

        except subprocess.TimeoutExpired:
            return False, None, f"LaTeX compilation timed out after {timeout} seconds"
        except Exception as exc:
            return False, None, f"LaTeX compilation process failure: {str(exc)}"


def _to_clean_str(val: Any) -> str:
    """Safely extracts a clean string from any value (string, dict, int, float, list)."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        for k in ("name", "title", "label", "text", "summary", "desc", "bullet", "value"):
            if val.get(k):
                return str(val[k]).strip()
        return ", ".join(f"{k}: {v}" for k, v in val.items() if v)
    return str(val).strip()


def _to_clean_bullets(raw: Any) -> List[str]:
    """Safely extracts a list of bullet strings from any input format."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in re.split(r"[\r\n]+", raw) if s.strip()]
    if isinstance(raw, list):
        res = []
        for item in raw:
            s = _to_clean_str(item)
            if s:
                clean_s = re.sub(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*", "", s).strip()
                res.append(clean_s if clean_s else s)
        return res
    s = _to_clean_str(raw)
    return [s] if s else []


def _render_with_reportlab(data: Dict[str, Any], title: str = "", template_slug: str = "ats-classic") -> bytes:
    """
    Renders structured resume JSON data into an authentic, template-matching PDF
    using ReportLab when a local pdflatex binary is not present on the host OS.
    Preserves the selected template's font, colors, headers, margins, and section styling.
    """
    import io
    import html
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    slug = template_slug.lower() if template_slug else "ats-classic"

    # Style Presets per template family for all 15 distinct designs
    if slug == "classic-ats" or slug == "ats-classic":
        font_main, font_bold, font_italic = "Times-Roman", "Times-Bold", "Times-Italic"
        primary_color = colors.HexColor("#000000")
        accent_color = colors.HexColor("#334155")
        align_title = 1 # Center
        margin = 32
    elif slug == "academic-cv":
        font_main, font_bold, font_italic = "Times-Roman", "Times-Bold", "Times-Italic"
        primary_color = colors.HexColor("#111827")
        accent_color = colors.HexColor("#475569")
        align_title = 1
        margin = 36
    elif slug == "executive-resume":
        font_main, font_bold, font_italic = "Times-Roman", "Times-Bold", "Times-Italic"
        primary_color = colors.HexColor("#14234b")
        accent_color = colors.HexColor("#1e3a8a")
        align_title = 1
        margin = 34
    elif slug == "graduate-fresher":
        font_main, font_bold, font_italic = "Times-Roman", "Times-Bold", "Times-Italic"
        primary_color = colors.HexColor("#0f172a")
        accent_color = colors.HexColor("#2563eb")
        align_title = 1
        margin = 32
    elif slug == "modern-corporate":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#1e40af") # Corporate Navy
        accent_color = colors.HexColor("#3b82f6")
        align_title = 0
        margin = 32
    elif slug == "modern-two-column":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#2563eb") # Royal Blue
        accent_color = colors.HexColor("#0284c7")
        align_title = 0
        margin = 28
    elif slug == "color-sidebar":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#0284c7") # Sky
        accent_color = colors.HexColor("#0369a1")
        align_title = 0
        margin = 24
    elif slug == "minimalist-elegant":
        font_main, font_bold, font_italic = "Times-Roman", "Times-Bold", "Times-Italic"
        primary_color = colors.HexColor("#1e293b") # Muted Slate
        accent_color = colors.HexColor("#64748b")
        align_title = 1
        margin = 36
    elif slug == "bold-creative":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#b91c1c") # Bold Red
        accent_color = colors.HexColor("#dc2626")
        align_title = 0
        margin = 30
    elif slug == "software-engineer":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#0284c7") # Cyan Tech
        accent_color = colors.HexColor("#0f172a")
        align_title = 0
        margin = 30
    elif slug == "ai-ml-engineer":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#6d28d9") # Violet
        accent_color = colors.HexColor("#8b5cf6")
        align_title = 1
        margin = 32
    elif slug == "data-scientist":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#4338ca") # Indigo
        accent_color = colors.HexColor("#6366f1")
        align_title = 1
        margin = 32
    elif slug == "developer-portfolio":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#0e7490") # Dark Cyan
        accent_color = colors.HexColor("#06b6d4")
        align_title = 0
        margin = 30
    elif slug == "timeline-resume":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#0369a1") # Ocean Blue
        accent_color = colors.HexColor("#0284c7")
        align_title = 0
        margin = 30
    elif slug == "infographic-resume":
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#5b21b6") # Deep Purple
        accent_color = colors.HexColor("#7c3aed")
        align_title = 0
        margin = 28
    else:
        font_main, font_bold, font_italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
        primary_color = colors.HexColor("#0f172a")
        accent_color = colors.HexColor("#2563eb")
        align_title = 1
        margin = 32

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ResumeTitle',
        parent=styles['Normal'],
        fontSize=18,
        leading=21,
        fontName=font_bold,
        alignment=align_title,
        textColor=primary_color
    )
    contact_style = ParagraphStyle(
        'ResumeContact',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
        fontName=font_main,
        alignment=align_title,
        textColor=colors.HexColor('#475569')
    )
    section_style = ParagraphStyle(
        'ResumeSection',
        parent=styles['Normal'],
        fontSize=10.5,
        leading=13.5,
        fontName=font_bold,
        textColor=primary_color,
        spaceBefore=6,
        spaceAfter=2
    )
    body_style = ParagraphStyle(
        'ResumeBody',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
        fontName=font_main,
        textColor=colors.HexColor('#1e293b')
    )
    bullet_style = ParagraphStyle(
        'ResumeBullet',
        parent=body_style,
        leftIndent=10,
        bulletIndent=3,
        spaceBefore=1,
        spaceAfter=1
    )
    item_header_style = ParagraphStyle(
        'ItemHeader',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=3
    )

    story = []

    # 1. Header (Personal Info)
    personal = data.get("personal_info", {})
    name = _to_clean_str(personal.get("full_name") or personal.get("name") or "Candidate Resume")
    story.append(Paragraph(html.escape(name), title_style))
    story.append(Spacer(1, 2))

    prof_title = personal.get("professional_title")
    if prof_title and str(prof_title).strip():
        subtitle_style = ParagraphStyle(
            'ResumeSubtitle',
            parent=styles['Normal'],
            fontSize=11,
            leading=13.5,
            fontName=font_bold,
            alignment=align_title,
            textColor=accent_color,
            spaceAfter=3
        )
        story.append(Paragraph(html.escape(str(prof_title).strip()), subtitle_style))
        story.append(Spacer(1, 2))

    contact_parts = []
    if personal.get("email"):
        contact_parts.append(html.escape(_to_clean_str(personal["email"])))
    if personal.get("phone"):
        contact_parts.append(html.escape(_to_clean_str(personal["phone"])))
    loc = personal.get("location") or personal.get("address")
    if loc:
        contact_parts.append(html.escape(_to_clean_str(loc)))
    if personal.get("linkedin"):
        contact_parts.append(f'<a href="{html.escape(_to_clean_str(personal["linkedin"]))}"><u>LinkedIn</u></a>')
    if personal.get("github"):
        contact_parts.append(f'<a href="{html.escape(_to_clean_str(personal["github"]))}"><u>GitHub</u></a>')

    if contact_parts:
        story.append(Paragraph(" &bull; ".join(contact_parts), contact_style))
        story.append(Spacer(1, 4))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=2, spaceAfter=5))

    # 2. Professional Summary
    raw_summary = data.get("summary") or data.get("professional_summary") or data.get("career_objective")
    summary = _to_clean_str(raw_summary)
    if summary and summary.strip():
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
        story.append(Paragraph(html.escape(summary.strip()), body_style))
        story.append(Spacer(1, 4))

    # 3. Technical Skills
    skills = data.get("skills")
    if skills:
        story.append(Paragraph("TECHNICAL SKILLS", section_style))
        if isinstance(skills, dict):
            for cat, s_list in skills.items():
                if isinstance(s_list, list):
                    items = [_to_clean_str(x) for x in s_list if _to_clean_str(x)]
                    items_str = ", ".join(items)
                elif isinstance(s_list, str):
                    items_str = s_list
                else:
                    items_str = _to_clean_str(s_list)
                if items_str:
                    story.append(Paragraph(f"<b>{html.escape(str(cat))}:</b> {html.escape(items_str)}", body_style))
        elif isinstance(skills, list):
            items = [_to_clean_str(x) for x in skills if _to_clean_str(x)]
            if items:
                story.append(Paragraph(html.escape(", ".join(items)), body_style))
        elif isinstance(skills, str) and skills.strip():
            story.append(Paragraph(html.escape(skills.strip()), body_style))
        story.append(Spacer(1, 4))

    # 4. Work Experience
    experience = data.get("experience") or data.get("work_experience") or []
    if experience and isinstance(experience, list):
        story.append(Paragraph("WORK EXPERIENCE", section_style))
        for exp in experience:
            if not isinstance(exp, dict):
                continue
            job_title = _to_clean_str(exp.get("title") or exp.get("role") or exp.get("designation") or "")
            company = _to_clean_str(exp.get("company") or exp.get("employer") or "")
            start_d = _to_clean_str(exp.get("start_date") or "")
            end_d = _to_clean_str(exp.get("end_date") or ("Present" if exp.get("is_current") else ""))
            dates = f"{start_d} &ndash; {end_d}".strip(" &ndash;") if (start_d or end_d) else ""
            loc = _to_clean_str(exp.get("location") or exp.get("employment_location") or "")
            loc_str = f" ({loc})" if loc else ""

            header_text = f"<b>{html.escape(job_title)}</b>" if job_title else ""
            if company:
                if header_text:
                    header_text += f" &mdash; <i>{html.escape(company)}</i>{loc_str}"
                else:
                    header_text = f"<b>{html.escape(company)}</b>{loc_str}"
            if dates:
                header_text += f' <font color="#64748b">[{dates}]</font>'

            if header_text:
                story.append(Paragraph(header_text, item_header_style))

            bullets = _to_clean_bullets(exp.get("bullets") or exp.get("responsibilities") or exp.get("highlights") or exp.get("description") or [])
            for b in bullets:
                story.append(Paragraph(f"&bull; {html.escape(b)}", bullet_style))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 4))

    # 5. Projects
    projects = canonicalize_projects_list(data.get("projects") or [])
    if projects and isinstance(projects, list):
        story.append(Paragraph("PROJECTS", section_style))
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            p_name = _to_clean_str(proj.get("name") or proj.get("title") or proj.get("project_name") or "")
            tech_raw = proj.get("tech_stack") or proj.get("technologies") or ""
            if isinstance(tech_raw, list):
                tech = ", ".join(_to_clean_str(t) for t in tech_raw if _to_clean_str(t))
            else:
                tech = _to_clean_str(tech_raw)
            start_d = _to_clean_str(proj.get("start_date") or "")
            end_d = _to_clean_str(proj.get("end_date") or proj.get("duration") or "")
            dates = f"{start_d} {end_d}".strip() or _to_clean_str(proj.get("dates") or "")

            p_header = f"<b>{html.escape(p_name)}</b>" if p_name else ""
            if tech:
                p_header += f" <font color='#475569'>| <i>{html.escape(tech)}</i></font>"
            if dates:
                p_header += f" <font color='#64748b'>[{dates}]</font>"
            if p_header:
                story.append(Paragraph(p_header, item_header_style))

            # Render distinct overview description if present
            p_desc = _to_clean_str(proj.get("description") or "")
            if p_desc:
                story.append(Paragraph(html.escape(p_desc), body_style))
                story.append(Spacer(1, 1))

            bullets = proj.get("bullets") or []
            for b in bullets:
                clean_b = clean_bullet_text(str(b))
                if clean_b:
                    story.append(Paragraph(f"&bull; {html.escape(clean_b)}", bullet_style))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 4))

    # 6. Education
    education = data.get("education") or []
    if education and isinstance(education, list):
        story.append(Paragraph("EDUCATION", section_style))
        for edu in education:
            if not isinstance(edu, dict):
                continue
            degree = _to_clean_str(edu.get("degree") or edu.get("field_of_study") or "")
            inst = _to_clean_str(edu.get("institution") or edu.get("university") or edu.get("school") or "")
            start_d = _to_clean_str(edu.get("start_date") or "")
            end_d = _to_clean_str(edu.get("end_date") or edu.get("graduation_year") or "")
            dates = f"{start_d} &ndash; {end_d}".strip(" &ndash;") if (start_d or end_d) else ""
            gpa_raw = _to_clean_str(edu.get("gpa") or edu.get("grade") or "")
            gpa = f"GPA: {gpa_raw}" if gpa_raw else ""

            edu_header = f"<b>{html.escape(degree)}</b>" if degree else ""
            if inst:
                if edu_header:
                    edu_header += f" &mdash; <i>{html.escape(inst)}</i>"
                else:
                    edu_header = f"<b>{html.escape(inst)}</b>"
            if dates:
                edu_header += f' <font color="#64748b">[{dates}]</font>'
            if gpa:
                edu_header += f' &bull; <font color="#475569">{gpa}</font>'
            if edu_header:
                story.append(Paragraph(edu_header, item_header_style))
        story.append(Spacer(1, 4))

    # 7. Certifications
    certs = data.get("certifications") or []
    if certs:
        story.append(Paragraph("CERTIFICATIONS", section_style))
        if isinstance(certs, list):
            for c in certs:
                if isinstance(c, dict):
                    c_name = _to_clean_str(c.get("name") or c.get("title") or "")
                    issuer = _to_clean_str(c.get("issuer") or c.get("issuing_organization") or "")
                    date_c = _to_clean_str(c.get("date") or c.get("issue_date") or "")
                    c_text = c_name
                    if issuer:
                        c_text += f" &mdash; {issuer}"
                    if date_c:
                        c_text += f" ({date_c})"
                    if c_text:
                        story.append(Paragraph(f"&bull; {html.escape(c_text)}", bullet_style))
                else:
                    c_str = _to_clean_str(c)
                    if c_str:
                        story.append(Paragraph(f"&bull; {html.escape(c_str)}", bullet_style))
        elif isinstance(certs, str) and certs.strip():
            story.append(Paragraph(html.escape(certs.strip()), body_style))

    doc.build(story)
    return buf.getvalue()


def _render_with_pymupdf(data: Dict[str, Any], title: str = "", template_slug: str = "ats-classic") -> bytes:
    """
    Zero-dependency / PyMuPDF fallback renderer for generating clean ATS vector PDFs
    when ReportLab is not installed or encounters an import failure in the container runtime.
    """
    import pymupdf

    doc = pymupdf.open()
    page_width, page_height = 612.0, 792.0  # Standard Letter
    margin_x = 36.0
    margin_y = 36.0

    page = doc.new_page(width=page_width, height=page_height)
    curr_y = margin_y + 16.0

    def check_page_break(needed_height: float):
        nonlocal page, curr_y
        if curr_y + needed_height > page_height - margin_y:
            page = doc.new_page(width=page_width, height=page_height)
            curr_y = margin_y + 16.0

    def draw_section_heading(heading_text: str):
        nonlocal curr_y
        check_page_break(32.0)
        curr_y += 8.0
        page.insert_text((margin_x, curr_y), heading_text, fontsize=10.5, fontname="helv", color=(0.1, 0.15, 0.3))
        curr_y += 4.0
        page.draw_line((margin_x, curr_y), (page_width - margin_x, curr_y), color=(0.2, 0.3, 0.5), width=0.75)
        curr_y += 12.0

    # 1. Personal Information Header
    personal = data.get("personal_info") or {}
    full_name = _to_clean_str(personal.get("full_name") or personal.get("name") or title or "Candidate Name")
    page.insert_text((margin_x, curr_y), full_name, fontsize=18, fontname="helv", color=(0.0, 0.0, 0.0))
    curr_y += 16.0

    contacts = []
    if personal.get("email"): contacts.append(_to_clean_str(personal["email"]))
    if personal.get("phone"): contacts.append(_to_clean_str(personal["phone"]))
    if personal.get("location") or personal.get("address"):
        contacts.append(_to_clean_str(personal.get("location") or personal.get("address")))
    if personal.get("linkedin"): contacts.append(_to_clean_str(personal["linkedin"]))
    if personal.get("github"): contacts.append(_to_clean_str(personal["github"]))

    if contacts:
        contact_line = "  |  ".join(contacts)
        page.insert_text((margin_x, curr_y), contact_line, fontsize=9.0, fontname="helv", color=(0.3, 0.3, 0.3))
        curr_y += 12.0

    page.draw_line((margin_x, curr_y), (page_width - margin_x, curr_y), color=(0.1, 0.15, 0.3), width=1.5)
    curr_y += 10.0

    # 2. Professional Summary
    summary_text = _to_clean_str(data.get("summary") or data.get("professional_summary") or data.get("career_objective") or "")
    if summary_text:
        draw_section_heading("PROFESSIONAL SUMMARY")
        check_page_break(25.0)
        words = summary_text.split()
        line = []
        for word in words:
            line.append(word)
            test_line = " ".join(line)
            if len(test_line) > 95:
                page.insert_text((margin_x, curr_y), test_line, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
                curr_y += 12.0
                check_page_break(14.0)
                line = []
        if line:
            page.insert_text((margin_x, curr_y), " ".join(line), fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
            curr_y += 14.0

    # 3. Skills & Technologies
    skills_data = data.get("skills")
    if skills_data:
        draw_section_heading("SKILLS & TECHNOLOGIES")
        if isinstance(skills_data, dict):
            for cat, items in skills_data.items():
                cat_str = _to_clean_str(cat)
                if isinstance(items, list):
                    items_str = ", ".join(_to_clean_str(x) for x in items if _to_clean_str(x))
                else:
                    items_str = _to_clean_str(items)
                if items_str:
                    check_page_break(15.0)
                    line_text = f"{cat_str}: {items_str}"
                    page.insert_text((margin_x, curr_y), line_text, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
                    curr_y += 13.0
        elif isinstance(skills_data, list):
            items_str = ", ".join(_to_clean_str(x) for x in skills_data if _to_clean_str(x))
            if items_str:
                check_page_break(15.0)
                page.insert_text((margin_x, curr_y), items_str, fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
                curr_y += 13.0
        elif isinstance(skills_data, str) and skills_data.strip():
            check_page_break(15.0)
            page.insert_text((margin_x, curr_y), skills_data.strip(), fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
            curr_y += 13.0

    # 4. Work Experience
    experience = data.get("experience") or data.get("work_experience") or []
    if experience and isinstance(experience, list):
        draw_section_heading("WORK EXPERIENCE")
        for exp in experience:
            if not isinstance(exp, dict):
                continue
            title_e = _to_clean_str(exp.get("title") or exp.get("designation") or exp.get("role") or "")
            comp_e = _to_clean_str(exp.get("company") or exp.get("employer") or "")
            dates_e = _to_clean_str(exp.get("dates") or f"{exp.get('start_date', '')} - {exp.get('end_date', '')}".strip(" -"))
            loc_e = _to_clean_str(exp.get("location") or exp.get("employment_location") or "")

            header_text = title_e
            if comp_e: header_text += f" - {comp_e}"
            if loc_e: header_text += f" ({loc_e})"
            if dates_e: header_text += f"  [{dates_e}]"

            if header_text:
                check_page_break(20.0)
                page.insert_text((margin_x, curr_y), header_text, fontsize=10, fontname="helv", color=(0.05, 0.1, 0.25))
                curr_y += 13.0

            bullets = _to_clean_bullets(exp.get("bullets") or exp.get("responsibilities") or exp.get("achievements") or [])
            for b in bullets:
                check_page_break(14.0)
                page.insert_text((margin_x + 10, curr_y), f"- {b}", fontsize=9, fontname="helv", color=(0.2, 0.2, 0.2))
                curr_y += 12.0
            curr_y += 4.0

    # 5. Projects
    projects = canonicalize_projects_list(data.get("projects") or [])
    if projects and isinstance(projects, list):
        draw_section_heading("PROJECTS")
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            p_name = _to_clean_str(proj.get("name") or proj.get("title") or "")
            tech_raw = proj.get("tech_stack") or proj.get("technologies") or ""
            if isinstance(tech_raw, list):
                tech = ", ".join(_to_clean_str(t) for t in tech_raw if _to_clean_str(t))
            else:
                tech = _to_clean_str(tech_raw)

            proj_header = p_name
            if tech: proj_header += f" | {tech}"

            if proj_header:
                check_page_break(18.0)
                page.insert_text((margin_x, curr_y), proj_header, fontsize=10, fontname="helv", color=(0.05, 0.1, 0.25))
                curr_y += 13.0

            p_desc = _to_clean_str(proj.get("description") or "")
            if p_desc:
                check_page_break(14.0)
                page.insert_text((margin_x + 5, curr_y), p_desc, fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))
                curr_y += 12.0

            bullets = proj.get("bullets") or []
            for b in bullets:
                clean_b = clean_bullet_text(str(b))
                if clean_b:
                    check_page_break(14.0)
                    page.insert_text((margin_x + 10, curr_y), f"- {clean_b}", fontsize=9, fontname="helv", color=(0.2, 0.2, 0.2))
                    curr_y += 12.0
            curr_y += 4.0

    # 6. Education
    education = data.get("education") or []
    if education and isinstance(education, list):
        draw_section_heading("EDUCATION")
        for edu in education:
            if not isinstance(edu, dict):
                continue
            degree = _to_clean_str(edu.get("degree") or edu.get("field_of_study") or "")
            inst = _to_clean_str(edu.get("institution") or edu.get("university") or "")
            dates = _to_clean_str(edu.get("dates") or f"{edu.get('start_date', '')} - {edu.get('end_date', '')}".strip(" -"))
            gpa = _to_clean_str(edu.get("gpa") or edu.get("grade") or "")

            edu_text = degree
            if inst: edu_text += f" - {inst}"
            if dates: edu_text += f" [{dates}]"
            if gpa: edu_text += f" (GPA: {gpa})"

            if edu_text:
                check_page_break(16.0)
                page.insert_text((margin_x, curr_y), edu_text, fontsize=9.5, fontname="helv", color=(0.1, 0.1, 0.1))
                curr_y += 13.0

    # 7. Certifications
    certs = data.get("certifications") or []
    if certs:
        draw_section_heading("CERTIFICATIONS")
        if isinstance(certs, list):
            for c in certs:
                if isinstance(c, dict):
                    c_name = _to_clean_str(c.get("name") or c.get("title") or "")
                    issuer = _to_clean_str(c.get("issuer") or "")
                    c_text = f"{c_name} - {issuer}" if issuer else c_name
                else:
                    c_text = _to_clean_str(c)
                if c_text:
                    check_page_break(14.0)
                    page.insert_text((margin_x + 10, curr_y), f"- {c_text}", fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))
                    curr_y += 12.0
        elif isinstance(certs, str) and certs.strip():
            check_page_break(14.0)
            page.insert_text((margin_x, curr_y), certs.strip(), fontsize=9.5, fontname="helv", color=(0.15, 0.15, 0.15))
            curr_y += 12.0

    return doc.tobytes()


def render_structured_data_to_pdf(data: Dict[str, Any], title: str = "", template_slug: str = "ats-classic") -> bytes:
    """
    Renders structured resume JSON data into an authentic, template-matching PDF.
    Attempts ReportLab first (primary Overleaf-grade renderer).
    If ReportLab is unavailable or encounters an import failure, seamlessly falls back to PyMuPDF.
    """
    try:
        return _render_with_reportlab(data, title, template_slug)
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(f"ReportLab import failed ({e}), falling back to PyMuPDF standalone vector engine")
        return _render_with_pymupdf(data, title, template_slug)


