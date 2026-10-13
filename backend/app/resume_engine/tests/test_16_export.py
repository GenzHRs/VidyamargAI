"""Comprehensive regression tests for One Resume = One Row Excel, CSV, and DB export."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import openpyxl

from resume_extract.export import (
    process_and_export,
    parse_resume_to_row,
    format_skills,
    format_education,
    format_experience,
    format_projects,
    format_certificates,
    classify_cert_type,
    EXPORT_COLUMNS,
)

ROOT = Path(__file__).resolve().parent


class ExportPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name) / "exports"
        self.db_path = self.out_dir / "test_candidates.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_single_resume_one_row_mapping(self):
        """Verify mock resume maps into exactly one dictionary row with expected column headers."""
        mock_data = {
            "source": {"filename": "john_doe.pdf", "sha256": "a" * 64, "type": "pdf", "duplicate_of": None},
            "quality": {"completeness": {"status": "pass"}, "schema_errors": []},
            "structured": {
                "contact": {
                    "name": {"value": "John Doe"},
                    "emails": [{"value": "john@example.com"}],
                    "phones": [{"value": "+1-555-1234"}],
                    "locations": [{"value": "Seattle, WA"}],
                    "links": [{"value": "https://linkedin.com/in/johndoe"}, {"value": "https://github.com/johndoe"}],
                },
                "summary": [{"value": "Experienced Software Engineer with a passion for AI."}],
                "skills": [{"category": "Languages", "items": ["Python", "Rust", "TypeScript"]}],
                "education": [
                    {
                        "degree": {"value": "B.S. Computer Science"},
                        "institution": {"value": "University of Washington"},
                        "dates": {"value": {"start": "2016", "end": "2020"}},
                        "gpa": {"value": {"score": "3.9", "scale": "4.0"}},
                    }
                ],
                "experience": [
                    {
                        "title": {"value": "Senior Engineer"},
                        "company": {"value": "Tech Corp"},
                        "dates": {"value": {"start": "2020", "end": "Present"}},
                        "bullets": ["Engineered distributed services.", "Improved throughput by 40%."],
                    }
                ],
                "projects": [
                    {
                        "name": {"value": "RAG Chatbot"},
                        "dates": {"value": {"start": "2023", "end": "2024"}},
                        "technologies": [{"value": "Python"}, {"value": "FastAPI"}],
                        "bullets": ["Built conversational AI assistant."],
                    }
                ],
                "certifications": [
                    {
                        "name": {"value": "AWS Solutions Architect"},
                        "details": "Amazon Web Services (2022)",
                    },
                    {
                        "name": {"value": "Deep Learning Specialization"},
                        "details": "Coursera / deeplearning.ai (2023)",
                    }
                ],
                "other_sections": [
                    {"canonical": "awards", "text": "Top Innovator 2023"}
                ]
            }
        }

        row = parse_resume_to_row(mock_data, default_id="CAND-01")
        self.assertEqual(row["Resume_ID"], "CAND-01")
        self.assertEqual(row["Candidate_Name"], "John Doe")
        self.assertEqual(row["Email"], "john@example.com")
        self.assertEqual(row["Phone"], "+1-555-1234")
        self.assertEqual(row["Location"], "Seattle, WA")
        self.assertEqual(row["LinkedIn"], "https://linkedin.com/in/johndoe")
        self.assertEqual(row["GitHub"], "https://github.com/johndoe")
        self.assertIn("Languages: Python, Rust, TypeScript", row["Skills"])
        self.assertIn("B.S. Computer Science - University of Washington", row["Education"])
        self.assertIn("Senior Engineer at Tech Corp", row["Experience"])
        self.assertIn("RAG Chatbot", row["Projects"])
        self.assertIn("[Certification] AWS Solutions Architect", row["Certificates"])
        self.assertIn("[Course] Deep Learning Specialization", row["Certificates"])
        self.assertEqual(row["Extraction_Status"], "Verified Pass")

    def test_multiple_entries_stay_in_same_cell(self):
        """Multiple jobs, degrees, projects, certificates must format within single multi-line strings."""
        edu_list = [
            {"degree": {"value": "M.S. CS"}, "institution": {"value": "MIT"}, "graduation": {"value": "2022"}},
            {"degree": {"value": "B.S. EE"}, "institution": {"value": "Stanford"}, "graduation": {"value": "2020"}},
        ]
        formatted_edu = format_education(edu_list)
        self.assertIn("M.S. CS - MIT", formatted_edu)
        self.assertIn("B.S. EE - Stanford", formatted_edu)
        # Verify both appear separated by double newline in the SAME string
        parts = formatted_edu.split("\n\n")
        self.assertEqual(len(parts), 2)

        exp_list = [
            {"title": {"value": "Lead Architect"}, "company": {"value": "Acme Inc"}, "bullets": ["Led team."]},
            {"title": {"value": "Staff Engineer"}, "company": {"value": "Beta LLC"}, "bullets": ["Built tools."]},
        ]
        formatted_exp = format_experience(exp_list)
        self.assertIn("Lead Architect at Acme Inc", formatted_exp)
        self.assertIn("Staff Engineer at Beta LLC", formatted_exp)
        self.assertEqual(len(formatted_exp.split("\n\n")), 2)

    def test_cert_type_classification_and_combination(self):
        """Certificates column must combine certifications, training, courses, and licenses."""
        self.assertEqual(classify_cert_type("AWS Certified SysOps"), "Certification")
        self.assertEqual(classify_cert_type("Machine Learning Course", "Coursera"), "Course")
        self.assertEqual(classify_cert_type("Advanced Data Science Training", "Bengaluru Bootcamp"), "Training")
        self.assertEqual(classify_cert_type("Certified Public Accountant (CPA)", "State Board License"), "License")

        certs = [
            {"name": "AWS Certified Developer", "details": ""},
            {"name": "Full Stack Web Development Training", "details": "Completed 6-week intensive"},
            {"name": "Neural Networks Course", "details": "Coursera certificate"},
        ]
        res = format_certificates(certs)
        self.assertIn("[Certification] AWS Certified Developer", res)
        self.assertIn("[Training] Full Stack Web Development Training", res)
        self.assertIn("[Course] Neural Networks Course", res)

    def test_corpus_export_row_count_and_deduplication(self):
        """Process new_structured_results and ensure exact row count equals unique resumes."""
        source_dir = ROOT.parent / "new_structured_results"
        if not source_dir.exists():
            self.skipTest("new_structured_results not generated yet")

        rows, stats = process_and_export([source_dir], self.out_dir, self.db_path)
        self.assertGreater(len(rows), 0)
        self.assertEqual(stats["unique_resumes"], len(rows))
        self.assertEqual(stats["total_files_examined"], stats["unique_resumes"] + stats["duplicates_skipped"])

        # Check file creation
        csv_file = self.out_dir / "resumes_one_row_per_candidate.csv"
        xlsx_file = self.out_dir / "resumes_one_row_per_candidate.xlsx"
        self.assertTrue(csv_file.exists())
        self.assertTrue(xlsx_file.exists())

        # Validate CSV contents
        with csv_file.open("r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), len(rows))
            for r in reader:
                self.assertTrue(r["Resume_ID"])
                self.assertTrue(r["Candidate_Name"])
                self.assertTrue(r["Source_File"])

        # Validate XLSX contents
        wb = openpyxl.load_workbook(xlsx_file)
        ws = wb.active
        excel_rows = list(ws.iter_rows(values_only=True))
        # 1 header row + len(rows) data rows
        self.assertEqual(len(excel_rows), len(rows) + 1)
        self.assertEqual(list(excel_rows[0]), EXPORT_COLUMNS)

        # Validate 1:1 CSV and Excel equivalence
        for i, data_dict in enumerate(rows, 1):
            excel_data = excel_rows[i]
            for col_idx, col_name in enumerate(EXPORT_COLUMNS):
                val_dict = data_dict.get(col_name) or ""
                val_excel = excel_data[col_idx] or ""
                self.assertEqual(val_dict, str(val_excel), f"Mismatch in row {i} col {col_name}")

        # Validate Database Relational Integrity
        conn = sqlite3.connect(self.db_path)
        cand_db_count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        self.assertEqual(cand_db_count, len(rows))

        # Check foreign keys
        orphan_edu = conn.execute("SELECT COUNT(*) FROM candidate_education WHERE resume_id NOT IN (SELECT resume_id FROM candidates)").fetchone()[0]
        orphan_exp = conn.execute("SELECT COUNT(*) FROM candidate_experience WHERE resume_id NOT IN (SELECT resume_id FROM candidates)").fetchone()[0]
        orphan_prj = conn.execute("SELECT COUNT(*) FROM candidate_projects WHERE resume_id NOT IN (SELECT resume_id FROM candidates)").fetchone()[0]
        orphan_cert = conn.execute("SELECT COUNT(*) FROM candidate_certificates WHERE resume_id NOT IN (SELECT resume_id FROM candidates)").fetchone()[0]
        self.assertEqual(orphan_edu, 0)
        self.assertEqual(orphan_exp, 0)
        self.assertEqual(orphan_prj, 0)
        self.assertEqual(orphan_cert, 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
