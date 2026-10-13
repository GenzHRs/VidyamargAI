from pathlib import Path
import tempfile
import unittest
from resume_extract.ingest import ingest, detect_type

class IngestTests(unittest.TestCase):
    def test_magic_over_extension_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.docx';p.write_bytes(b'%PDF-1.4\n')
            seen={};a=ingest(p,seen);b=ingest(p,seen)
            self.assertEqual(a.kind,'pdf');self.assertIsNone(a.duplicate_of)
            self.assertEqual(b.duplicate_of,str(p));self.assertEqual(len(a.sha256),64)
    def test_text_and_reject_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data';p.write_text('Resume α',encoding='utf-8');self.assertEqual(detect_type(p),'txt')
            p.write_bytes(b'\x00\xff');self.assertRaises(ValueError,detect_type,p)
