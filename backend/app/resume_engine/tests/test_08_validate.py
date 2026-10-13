import unittest
from resume_extract.validate import completeness,needs_review,validate_schema
from resume_extract.config import load_config

class ValidationTests(unittest.TestCase):
    def test_multiset_no_dedup_cheat(self):
        c=load_config();r=completeness('one one two','one two three',c)
        self.assertEqual(r['status'],'fail');self.assertEqual(r['missing'],{'one':1});self.assertEqual(r['extra'],{'three':1})
    def test_review_and_schema(self):
        review=needs_review({'name':{'value':'Ambiguous','confidence':0.65}},[],load_config())
        self.assertEqual(review[0]['path'],'fields.name')
        self.assertTrue(validate_schema({'schema_version':'invalid'}))
    def test_nested_field_types_and_confidence_range(self):
        from resume_extract.pipeline import extract
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.txt';p.write_text('Jane Doe\nEngineer\njane@example.com')
            r=extract(p)
        r['fields']['emails'][0]['value']=42
        r['fields']['emails'][0]['confidence']=1.2
        errors=validate_schema(r)
        self.assertTrue(any('value' in e for e in errors));self.assertTrue(any('maximum' in e for e in errors))
