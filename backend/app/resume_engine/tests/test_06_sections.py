import unittest
from resume_extract.sections import canonical_heading,build_sections
from resume_extract.models import Line
from resume_extract.config import load_config

class SectionTests(unittest.TestCase):
    def test_synonym_fuzzy_custom_no_loss(self):
        c=load_config();self.assertEqual(canonical_heading('CAREER HISTORY',c)[0],'experience')
        self.assertEqual(canonical_heading('PROFESSIONAL EXPERIANCE',c)[0],'experience')
        lines=[Line('a','COMMUNITY LAB',tag='H1'),Line('b','Unusual content')]
        s=build_sections(lines,c);self.assertEqual(s[0]['canonical'],'custom');self.assertEqual(s[0]['text'],'Unusual content')
