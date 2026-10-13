import unittest
from resume_extract.models import Line,Run
from resume_extract.config import load_config
from resume_extract.classify import classify

class ClassifyTests(unittest.TestCase):
    def test_normal_style_inline_label_and_unknown(self):
        lines=[Line('0','Jane Doe',[Run('Jane Doe',size=24)],source_ids=['0']),Line('1','Engineer',[Run('Engineer',size=11)]),Line('2','EXECUTIVE SUMMARY: Built things',[Run('x',size=11)]),Line('3','COMMUNITY LAB',[Run('x',bold=True,size=13)]),Line('4','Text here',[Run('x',size=11)])]
        out=classify(lines,load_config())
        self.assertEqual([l.tag for l in out],['TITLE','SUBTITLE','H1','TEXT','H1','TEXT'])
        self.assertEqual(out[2].text,'EXECUTIVE SUMMARY:');self.assertEqual(out[3].text,'Built things')
