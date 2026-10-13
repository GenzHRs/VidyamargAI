import unittest
from pathlib import Path
import json
from resume_extract.pipeline import extract
from resume_extract.config import load_config
from resume_extract.validate import completeness

ROOT=Path(__file__).parent/'fixtures'

class LayoutFixtureTests(unittest.TestCase):
    def test_all_digital_fixtures_preserve_words(self):
        for name in ['two_column_sidebar.pdf','horizontal_hero.pdf','dark_background.pdf','heavy_table.pdf','academic_repeated_margins.pdf','docx_edge_cases.docx']:
            with self.subTest(name=name):
                result=extract(ROOT/name)
                self.assertFalse(result['source']['ocr'])
                self.assertEqual(result['quality']['completeness']['status'],'pass',result['quality']['completeness'])
                self.assertEqual(result['quality']['schema_errors'],[])
    def test_column_order_and_light_text(self):
        result=extract(ROOT/'two_column_sidebar.pdf')
        raw=result['raw_text'];self.assertLess(raw.index('Docker Linux'),raw.index('JANE DOE'))
        hero=extract(ROOT/'horizontal_hero.pdf')['raw_text']
        self.assertLess(hero.index('SUMMARY'),hero.index('EXPERIENCE'));self.assertLess(hero.index('Delivered reliable services.'),hero.index('SKILLS'))
        dark=extract(ROOT/'dark_background.pdf');self.assertEqual(dark['fields']['name']['value'],'JANE DOE')
    def test_repeated_headers_auditable(self):
        result=extract(ROOT/'academic_repeated_margins.pdf')
        self.assertEqual(result['raw_text'].count('Confidential resume'),2)
        self.assertEqual(result['normalized_text'].count('Confidential resume'),1)
        self.assertEqual(result['raw_text'].count('JANE DOE'),2)
        self.assertEqual(result['normalized_text'].count('JANE DOE'),1)
    def test_scanned_local_ocr(self):
        import shutil
        if not shutil.which('tesseract'):
            self.skipTest('tesseract not installed or not on PATH')
        result=extract(ROOT/'scanned.pdf')
        self.assertTrue(result['source']['ocr']);self.assertEqual(result['source']['ocr_pages'],[1])
        self.assertEqual(result['quality']['completeness']['status'],'unverifiable')
        measured=completeness((ROOT/'scanned_gold.txt').read_text(),result['raw_text'],load_config())
        report=Path(__file__).parents[1]/'reports/ocr_fixture.json';report.write_text(json.dumps(measured,indent=2)+'\n')
        # This fixture has a verified transcript; OCR reliability elsewhere is not asserted.
        self.assertEqual(result['fields']['name']['value'],'JANE DOE')
        self.assertGreaterEqual(measured['recall'],0.95)
