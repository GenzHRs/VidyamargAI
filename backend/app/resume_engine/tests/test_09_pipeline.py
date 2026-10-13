import unittest
import tempfile
from pathlib import Path
from resume_extract.pipeline import extract,write_outputs

class PipelineTests(unittest.TestCase):
    def test_determinism_outputs_schema_and_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'resume.txt';p.write_text('Jane Doe\nEngineer\nSUMMARY\nExperienced engineer\nSKILLS\nPython, JS\n')
            a=extract(p);b=extract(p)
            self.assertEqual(a,b);self.assertEqual(a['quality']['schema_errors'],[])
            self.assertEqual(a['quality']['completeness']['status'],'pass')
            write_outputs(a,Path(d)/'out');self.assertTrue((Path(d)/'out/resume.md').exists())
