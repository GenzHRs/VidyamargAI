import unittest
from resume_extract.normalize import normalize,normalize_text
from resume_extract.models import Line,Run
from resume_extract.config import load_config

class NormalizeTests(unittest.TestCase):
    def test_bullets_ligatures_and_contacts(self):
        c=load_config();self.assertEqual(normalize_text('(cid:127) ﬁle',c),'• file')
        a=[Line(str(i),t,source_ids=[str(i)]) for i,t in enumerate(['City, ST','me@example.com','2021 –','Present'])]
        b=normalize(a,c)
        self.assertEqual([x.text for x in b],['City, ST','me@example.com','2021 – Present'])
        self.assertEqual(a[-2].text,'2021 –')
    def test_tight_prose_and_column_boundary(self):
        c=load_config();a=Line('1','We built a large production', [Run('x',size=10)],bbox=(0,0,100,10),source_ids=['1'])
        b=Line('2','platform', [Run('x',size=10)],bbox=(0,12,100,22),source_ids=['2'])
        self.assertEqual(len(normalize([a,b],c)),1)
        b.flow='sidebar';self.assertEqual(len(normalize([a,b],c)),2)
    def test_exact_margin_repeats_only(self):
        a=[Line('1','Name',part='header'),Line('2','Name',part='body'),Line('3','Name',part='header'),Line('4','Name 2',part='header')]
        b=normalize(a,load_config());self.assertEqual(b[2].duplicate_of,'1');self.assertIsNone(b[1].duplicate_of);self.assertIsNone(b[3].duplicate_of)
