"""General failure-class tests. No audit names/filenames in runtime rules."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import subprocess
import sys
from resume_extract.models import Line,Run,Document
from resume_extract.pipeline import process_document
from resume_extract.understanding import settings,understand_artifact,normalized_date
from resume_extract.understand_cli import run,store,inventory,load_profile
from resume_extract.validate import validate_schema


class UnderstandingTests(unittest.TestCase):
    def make(self,directory,lines):
        if isinstance(lines,str):lines=[Line('',t) for t in lines.splitlines()]
        for i,l in enumerate(lines):l.id=f'l{i}';l.source_ids=[l.id]
        raw='\n'.join(l.text for l in lines)
        result=process_document(Document(lines,raw,'decoded_text'),{'sha256':hashlib.sha256(raw.encode()).hexdigest(),'kind':'txt'},'arbitrary.txt',settings())
        p=Path(directory)/'resume.json';p.write_text(json.dumps(result),encoding='utf-8');return p

    def test_ignores_wrong_saved_structure_and_keeps_raw(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nelena@example.org\nEducation\nB.S. in Biology\nHarbor University\n2017 – 2021')
            original=json.loads(p.read_text());original['structured']['contact']['name']['value']='WRONG GROUND TRUTH'
            p.write_text(json.dumps(original),encoding='utf-8');before=p.read_bytes();r,u=understand_artifact(p)
            self.assertEqual(r['structured']['contact']['name']['value'],'ELENA RIVERA')
            self.assertEqual(p.read_bytes(),before);self.assertEqual(r['raw_text'],original['raw_text'])

    def test_bold_sentence_continuation_is_not_project(self):
        with tempfile.TemporaryDirectory() as d:
            lines=[Line('',t) for t in ['ELENA RIVERA','Projects']]
            for text,y,bold in [('Telemetry Monitor 2021 – 2022',20,True),('– Improved coverage to 88% with',40,False),('repeatable checks .',52,True),('– Documented deployment.',66,False)]:
                lines.append(Line('',text,runs=[Run(text,bold=bold,size=10)],bbox=(20,y,300,y+10)))
            p=self.make(d,lines);r,u=understand_artifact(p)
            self.assertEqual(len(r['structured']['projects']),1)
            self.assertEqual(r['structured']['projects'][0]['bullets'][0],'Improved coverage to 88% with repeatable checks.')
            self.assertIn('repeatable checks .',u['raw_text'])

    def test_company_first_header(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nExperience\nHarbor Systems LLC\nData Engineer\n2021 – 2023\n– Built data services.')
            r,u=understand_artifact(p);job=r['structured']['experience'][0]
            self.assertEqual(job['title']['value'],'Data Engineer');self.assertEqual(job['company']['value'],'Harbor Systems LLC')

    def test_certificate_details_and_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            lines=[Line('',t) for t in ['ELENA RIVERA','Certifications','Cloud Operations Certificate Trained in Linux, networks, and monitoring.']]
            lines[-1].runs=[Run(lines[-1].text,hyperlink='https://example.org/credential/42')]
            p=self.make(d,lines);r,u=understand_artifact(p)
            self.assertEqual(r['structured']['contact']['links'],[])
            cert=u['profile']['certifications'][0]
            self.assertEqual(cert['name']['value'],'Cloud Operations Certificate')
            self.assertTrue(cert['details'].startswith('Trained in'))
            self.assertEqual(cert['links'][0]['value'],'https://example.org/credential/42')
            conn=sqlite3.connect(':memory:');m=store(conn,r,u)
            self.assertIn('https://example.org/credential/42',m['profile']['certifications'][0]['links'])

    def test_internships_training_languages_and_unknown_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nInternships\nResearch Intern | Harbor Labs\n2021 – 2022\n– Tested samples.\nTraining\n• Laboratory Safety\nLanguages\nSpanish: Native\nEnglish: Fluent\nOTHER NOTES\nAvailable on weekends.')
            r,u=understand_artifact(p)
            self.assertEqual(len(u['profile']['internships']),1);self.assertEqual(len(u['profile']['training']),1)
            self.assertEqual([x['name'] for x in u['profile']['languages']],['Spanish','English'])
            self.assertIn('Available on weekends.',json.dumps(u['profile']['other_sections']))

    def test_plain_project_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nProjects\nTelemetry Monitor\n2021 – 2022\n– Built sensors.\nForecast Dashboard\n2023 – Present\nTech: Python, SQL\n– Added forecasts.')
            r,u=understand_artifact(p)
            self.assertEqual([x['name']['value'] for x in r['structured']['projects']],['Telemetry Monitor','Forecast Dashboard'])

    def test_date_precision(self):
        self.assertEqual(normalized_date('2023')['value'],'2023')
        self.assertEqual(normalized_date('Sep 2023')['value'],'2023-09')
        self.assertEqual(normalized_date('Present'),{'raw':'Present','value':None,'precision':'open'})
        self.assertIsNone(normalized_date('unknown')['value'])

    def test_no_input_tree_writes(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nSummary\nBuilds reliable services.')
            with self.assertRaises(ValueError):run(Path(d),Path(d)/'new_results')
            with self.assertRaises(ValueError):run(p,Path(d).parent/'output',db=Path(d)/'db.sqlite')

    def test_source_selection_prefers_raw_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nSummary\nBuilds reliable services.')
            (Path(d)/'raw.txt').write_text('raw',encoding='utf-8');(Path(d)/'structured.json').write_text('{"name":"wrong"}',encoding='utf-8')
            rows,selected=inventory(d);self.assertEqual(len(rows),3);self.assertEqual(selected[0]['path'],str(p))

    def test_flat_folder_keeps_distinct_resume_identities(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nSkills\nPython');first=json.loads(p.read_text())
            second=copy.deepcopy(first);second['source']['sha256']='2'*64
            (Path(d)/'second.json').write_text(json.dumps(second),encoding='utf-8')
            rows,selected=inventory(d);self.assertEqual(len(selected),2)

    def test_invalid_source_digest_cannot_control_output_path(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nSkills\nPython');data=json.loads(p.read_text())
            data['source']['sha256']='../../elsewhere';p.write_text(json.dumps(data),encoding='utf-8')
            r,u=understand_artifact(p)
            self.assertEqual(r['source']['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())

    def test_database_idempotency_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nSkills\nTools: Python, SQL');r,u=understand_artifact(p)
            conn=sqlite3.connect(':memory:');store(conn,r,u);store(conn,r,u)
            self.assertEqual(conn.execute('SELECT count(*) FROM profiles').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM resume_understandings').fetchone()[0],1)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            pid=conn.execute('SELECT profile_id FROM profiles').fetchone()[0]
            self.assertEqual(load_profile(conn,pid)['understanding'],u)
            changed=copy.deepcopy(u);changed['comparison']['changed']=not changed['comparison']['changed'];store(conn,r,changed)
            self.assertEqual(load_profile(conn,pid)['understanding'],changed)
            self.assertEqual(conn.execute('SELECT count(*) FROM resume_understandings').fetchone()[0],2)

    def test_separate_plain_text_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nCertifications\nCertified Systems Associate\nCertified Network Specialist\nTraining in routing and diagnostics.')
            r,u=understand_artifact(p)
            self.assertEqual([x['name']['value'] for x in r['structured']['certifications']],
                             ['Certified Systems Associate','Certified Network Specialist'])

    def test_license_status_is_not_a_second_credential(self):
        for metadata in ('Active License / Enrollment','License #12481'):
            with self.subTest(metadata=metadata),tempfile.TemporaryDirectory() as d:
                p=self.make(d,'ELENA RIVERA\nCertifications\nCertified Systems Associate\n'+metadata)
                r,u=understand_artifact(p);self.assertEqual(len(r['structured']['certifications']),1)
                self.assertIn(metadata,r['structured']['certifications'][0]['details'])

    def test_exact_entities_and_all_evidence_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nelena@example.org\nSkills\nTools: Python, SQL');r,u=understand_artifact(p)
            raw={l['id']:l for l in u['raw_lines']}
            for e in u['entities']:
                if e['source_kind']=='text':self.assertEqual(raw[e['source_line_id']]['text'][e['start']:e['end']],e['text'])
            for ev in u['evidence'].values():
                self.assertTrue(ev['source_refs'])
                for ref in ev['source_refs']:self.assertEqual(raw[ref['line_id']]['text'][ref['start']:ref['end']],ref['text'])
            schema=json.loads(Path(__file__).resolve().parents[1].joinpath('resume_extract/understanding.schema.json').read_text())
            self.assertEqual(validate_schema(u,schema),[])

    def test_validation_does_not_invent_missing_employer(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make(d,'ELENA RIVERA\nExperience\nResearch Intern\n2021 – 2020\n– Tested samples.')
            r,u=understand_artifact(p)
            self.assertIsNone(r['structured']['experience'][0]['company']['value'])
            self.assertIn('reversed_dates',[x['code'] for x in u['validation']['issues']])

    def test_external_evaluator_freezes_annotations_and_rejects_known_sources(self):
        # A synthetic harness test, NOT an independent real-world holdout score.
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'input';source.mkdir();p=self.make(source,'ELENA RIVERA\nSkills\nTools: Python, SQL')
            data=json.loads(p.read_text());gold={'contact':{'name':'ELENA RIVERA','emails':[],'phones':[],'locations':[],'links':[]},
                'experience':[],'education':[],'projects':[],'certifications':[],
                'skills':[{'category':'Tools','items':['Python','SQL']}],'headings':[{'text':'Skills'}]}
            label={'annotation_method':'manual_source_review','documents':[{'artifact':'input/resume.json','source_sha256':data['source']['sha256'],'gold':gold}]}
            labels=Path(d)/'labels.json';labels.write_text(json.dumps(label),encoding='utf-8');before=labels.read_bytes()
            command=[sys.executable,str(root/'ner_audit/evaluate_unseen.py'),str(labels),'--out',str(Path(d)/'out')]
            run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(run.returncode,0,run.stderr)
            report=json.loads((Path(d)/'out/unseen_metrics.json').read_text())
            self.assertEqual(report['field_mapping']['f1'],1);self.assertFalse(report['population_accuracy_claim'])
            self.assertEqual((Path(d)/'out/frozen_annotations.json').read_bytes(),before)
            known=json.loads((root/'ner_audit/manifest.json').read_text())[0]['sha256']
            label['documents'][0]['source_sha256']=known;labels.write_text(json.dumps(label),encoding='utf-8')
            run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8');self.assertEqual(run.returncode,2)
            self.assertIn('Known regression document',run.stderr)


if __name__=='__main__':unittest.main()
