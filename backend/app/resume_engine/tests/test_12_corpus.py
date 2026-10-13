import unittest
from pathlib import Path
import json
from unittest.mock import patch
from resume_extract.pipeline import extract
from resume_extract.config import load_config

class CorpusTests(unittest.TestCase):
    def test_supplied_files_completeness_schema_and_determinism_offline(self):
        root=Path(__file__).parent
        with patch('socket.socket.connect',side_effect=AssertionError('Network is forbidden at runtime')):
            for goldfile in sorted((root/'gold').glob('*.json')):
                gold=json.loads(goldfile.read_text());path=root/'corpus'/gold['file']
                with self.subTest(file=gold['file']):
                    a=extract(path);b=extract(path)
                    self.assertEqual(a,b)
                    self.assertEqual(a['quality']['completeness']['status'],'pass')
                    self.assertEqual(a['quality']['schema_errors'],[])
                    headings=[{'text':s['original_heading'],'canonical':s['canonical']} for s in a['sections'] if s['original_heading']]
                    self.assertEqual(headings,gold['headings'])
                    self.assertEqual(a['fields']['name']['value'],gold['fields']['name'])
