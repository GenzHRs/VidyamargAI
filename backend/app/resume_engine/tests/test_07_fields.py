import unittest
from resume_extract.config import load_config
from resume_extract.fields import extract_fields
from resume_extract.models import Line

class FieldTests(unittest.TestCase):
    def test_contacts_alias_dates_and_gpa(self):
        ls=[Line('1','me@example.com | +1 (415) 555-0199 | San Francisco, CA | github.com/test',source_ids=['1']),Line('2','JS Python | Jan 2021 - Present | 01/2020 – Current | 2018–2021 | GPA: 3.8 / 4.0',source_ids=['2'])]
        out=extract_fields(ls,[{'canonical':'preamble','line_ids':['1','2']}],load_config())
        self.assertEqual(len(out['date_ranges']),3);self.assertEqual(out['skills'][0]['value'],'Python')
        self.assertIn('JavaScript',[f['value'] for f in out['skills']]);self.assertEqual(out['locations'][0]['value'],'San Francisco, CA')
        self.assertEqual(out['gpas'][0]['value']['score'],'3.8')
    def test_grid_job(self):
        ls=[Line('1','2021 – Present',table='t',row=1,cell=0,source_ids=['1']),Line('2','Audit Controller',table='t',row=1,cell=1,source_ids=['2']),Line('3','Example LLP',table='t',row=1,cell=1,source_ids=['3']),Line('4','• Led team',table='t',row=1,cell=2,tag='BULLET',source_ids=['4'])]
        out=extract_fields(ls,[{'canonical':'experience','line_ids':['1','2','3','4']}],load_config())
        self.assertEqual(len(out['experience']),1);self.assertEqual(out['experience'][0]['company']['value'],'Example LLP')
