import json
from pathlib import Path
import unittest
from resume_extract.pipeline import extract, reprocess_result
from resume_extract.config import load_config
from resume_extract.models import Line, Run
from resume_extract.reading_order import repair_order
from resume_extract.fields import extract_fields

ROOT=Path(__file__).parent
class StructureTests(unittest.TestCase):
    def test_uploaded_sample_assignments(self):
        original=json.loads((ROOT/'samples/uploaded_result.json').read_text(encoding='utf-8'))
        r=reprocess_result(ROOT/'samples/uploaded_result.json');s=r['structured']
        self.assertEqual(r['raw_text'],original['raw_text'])
        self.assertEqual(r['raw_lines'],original['raw_lines'])
        self.assertEqual(r['quality']['schema_errors'],[])
        self.assertEqual(s['contact']['emails'][0]['value'],'j.shivachary@gmail.com')
        self.assertEqual(s['contact']['phones'][0]['normalized'],'+919866862016')
        self.assertEqual(len(s['education']),3)
        self.assertEqual([x['dates']['value'] for x in s['education']],[
            {'start':'September 2020','end':'April 2024'},
            {'start':'June 2018','end':'Feb 2020'},
            {'start':'June 2017','end':'Mar 2018'}])
        self.assertEqual([x['gpa']['value']['score'] for x in s['education']],['7.9','9.13','9.7'])
        self.assertEqual(len(s['experience']),1)
        job=s['experience'][0]
        self.assertEqual(job['title']['value'],'AI/ML Virtual Intern')
        self.assertIsNone(job['company']['value'])
        self.assertEqual(job['dates']['value'],{'start':'May 2023','end':'July 2023'})
        self.assertEqual(len(job['bullets']),4)
        self.assertIn('(15,000+ rows).',job['bullets'][0])
        self.assertEqual(len(s['projects']),2)
        self.assertEqual([len(x['bullets']) for x in s['projects']],[5,4])
        self.assertEqual(sum(len(x['items']) for x in s['skills']),15)
        self.assertEqual(len(s['certifications']),1)
        raw_ids={x['id'] for x in r['raw_lines']}
        def audit(value):
            if isinstance(value,dict):
                if 'source_line_ids' in value:self.assertTrue(set(value['source_line_ids'])<=raw_ids)
                for x in value.values():audit(x)
            elif isinstance(value,list):
                for x in value:audit(x)
        audit(s)
        self.assertEqual(r,reprocess_result(ROOT/'samples/uploaded_result.json'))

    def test_real_sidebar_not_globally_sorted(self):
        r=extract(ROOT/'fixtures/two_column_sidebar.pdf')
        self.assertLess(r['normalized_text'].index('Docker Linux'),r['normalized_text'].index('JANE DOE'))

    def test_ambiguous_text_dates_not_assigned(self):
        lines=[Line(str(i),t,source_ids=[str(i)]) for i,t in enumerate([
            'AI Intern','2017 - 2018','2023 - 2024','• Built tools'])]
        lines[-1].tag='BULLET'
        f=extract_fields(lines,[{'canonical':'experience','line_ids':[l.id for l in lines]}],load_config())
        self.assertEqual(len(f['experience']),1)
        self.assertIsNone(f['experience'][0]['dates']['value'])

    def test_inline_education_and_graduation(self):
        root=ROOT/'corpus/colorful_resume_templates_bundle'
        s=extract(root/'02_DOCX_Navy_Teal_Cloud_Architect.docx')['structured']
        self.assertEqual(s['education'][0]['degree']['value'],'M.S. in Computer Science')
        self.assertEqual(s['education'][0]['institution']['value'],'University of Colorado Boulder')
        self.assertEqual(s['education'][0]['graduation']['value'],'2017')

    def test_table_credentials_and_wrapped_institution(self):
        s=extract(ROOT/'corpus/comprehensive_resume_test_suite/05_PDF_Strict_Table_Grid_Resume.pdf')['structured']
        self.assertEqual(len(s['education']),1)
        self.assertEqual(s['education'][0]['institution']['value'],'Boston College — Carroll School of Management')
        self.assertTrue(any('Certified Public Accountant' in c['name']['value'] for c in s['certifications']))

    def test_inline_date_range_does_not_split_institution(self):
        s=extract(ROOT/'corpus/resume_templates_test_bundle/01_Modern_Tech_Software_Engineer.docx')['structured']
        self.assertEqual(s['education'][0]['institution']['value'],'University of California, Berkeley')
        self.assertEqual(s['education'][0]['dates']['value'],{'start':'2014','end':'2018'})

    def test_undated_and_ambiguous_jobs_are_valid_reviewable_results(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            p=Path(temp)/'resume.txt'
            for dates in ['', '2017 - 2018\n2023 - 2024\n']:
                p.write_text('JANE DOE\nExperience\nAI Intern\n'+dates+'• Built tools\n',encoding='utf-8')
                r=extract(p)
                self.assertEqual(r['quality']['schema_errors'],[])
                self.assertEqual(len(r['structured']['experience']),1)
                self.assertIsNone(r['structured']['experience'][0]['dates']['value'])
                self.assertTrue(any('dates' in v['path'] for v in r['structured']['review']))
