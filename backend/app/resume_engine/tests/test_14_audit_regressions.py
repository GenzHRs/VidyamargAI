"""Generalized fixtures for failure classes; no corpus names or labels in rules."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from resume_extract.config import load_config
from resume_extract.models import Line, Run, Document
from resume_extract.normalize import normalize
from resume_extract.pdf_reader import word_lines
from resume_extract.pipeline import process_document, extract
from resume_extract.text_rules import split_top_level, split_institution_location


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config()

    def process(self, lines):
        for i,line in enumerate(lines):line.id=f'l{i}';line.source_ids=[line.id]
        text='\n'.join(l.text for l in lines)
        result=process_document(Document(lines,text,'decoded_text'),{'sha256':'fixture','kind':'txt'},'fixture.txt',self.cfg)
        self.assertEqual(result['quality']['schema_errors'],[])
        return result['structured']

    def test_nested_skill_lists(self):
        self.assertEqual(split_top_level('Cloud (AWS, Azure [IaaS, PaaS]), C++, R&D; CI/CD'),
                         ['Cloud (AWS, Azure [IaaS, PaaS])','C++','R&D','CI/CD'])
        self.assertEqual(split_top_level('Research (incomplete, source'),['Research (incomplete, source'])

    def test_font_subset_bold(self):
        for font in ['XYZABC+CMBX10','CMSSBX10','ABCDEF+Helvetica-Bold']:
            words=[{'text':'Example','fontname':font,'size':10,'x0':10,'x1':50,'top':20,'bottom':30}]
            self.assertTrue(word_lines(words,self.cfg,{})[0].bold)

    def test_bullet_wrap_capitalized_and_numeric(self):
        for tail in ['42%.','API response time.','Zürich office.']:
            lines=[Line('a','– Improved processing latency by',runs=[Run('text',size=10)],bbox=(10,10,250,20),source_ids=['a']),
                   Line('b',tail,runs=[Run(tail,size=10)],bbox=(20,22,150,32),source_ids=['b']),
                   Line('c','– Another result.',runs=[Run('text',size=10)],bbox=(10,34,220,44),source_ids=['c'])]
            result=normalize(lines,self.cfg)
            self.assertEqual(len(result),2)
            self.assertTrue(result[0].text.endswith(tail))
            self.assertEqual(result[0].source_ids,['a','b'])

    def test_table_skill_column_ownership(self):
        lines=[Line('',t) for t in ['ALINA KIM','Skills']]
        for col,title in enumerate(['Platforms','Leadership']):
            lines.append(Line('',title,runs=[Run(title,bold=True,size=10)],table='t',row=0,cell=col))
        for col,text in enumerate(['Cloud (Azure, AWS), Linux','Mentoring, Budgeting']):
            lines.append(Line('',text,table='t',row=1,cell=col))
        s=self.process(lines)
        self.assertEqual([(x['category'],x['items']) for x in s['skills']],
            [('Platforms',['Cloud (Azure, AWS)','Linux']),('Leadership',['Mentoring','Budgeting'])])

    def test_education_metadata_not_institution(self):
        lines=[Line('',t) for t in ['ALINA KIM','Education']]
        lines += [Line('',t,table='t',row=0,cell=0) for t in
                  ['M.S. in Biology','Northern University','Graduated: 2022','CGPA: 8.4 / 10']]
        s=self.process(lines)['education'][0]
        self.assertEqual(s['institution']['value'],'Northern University')
        self.assertEqual(s['gpa']['value'],{'score':'8.4','scale':'10'})
        self.assertEqual(s['graduation']['value'],'2022')

    def test_locations_and_campus_names(self):
        self.assertEqual(split_institution_location('Northern University, Cedar City, UT'),('Northern University','Cedar City, UT'))
        self.assertEqual(split_institution_location('University of California, Davis'),('University of California, Davis',None))
        self.assertEqual(split_institution_location('Northern University — School of Arts'),('Northern University — School of Arts',None))

    def test_project_dates_and_technologies(self):
        s=self.process([Line('',t,runs=[Run(t,bold=b,size=10)]) for t,b in [
            ('ALINA KIM',True),('Projects',False),('Inventory Search Sept 2022 – June 2023',True),
            ('Tech: Rust, SQL (PostgreSQL, SQLite)',False),('– Built search.',False),
            ('Forecast Tool July 2023 – Present',True),('Technologies: R, Shiny',False),('– Improved forecasts.',False)]])
        self.assertEqual([p['name']['value'] for p in s['projects']],['Inventory Search','Forecast Tool'])
        self.assertEqual(s['projects'][0]['dates']['value'],{'start':'Sept 2022','end':'June 2023'})
        self.assertEqual([t['value'] for t in s['projects'][0]['technologies']],['Rust','SQL (PostgreSQL, SQLite)'])
        self.assertEqual([len(p['bullets']) for p in s['projects']],[1,1])

    def test_certification_list_and_prose(self):
        s=self.process([Line('',t) for t in ['ALINA KIM','Certifications',
            'Certified Cloud Developer (CCD, 2025), Certified Analytics Specialist (2024)']])
        self.assertEqual([c['name']['value'] for c in s['certifications']],
            ['Certified Cloud Developer (CCD, 2025)','Certified Analytics Specialist (2024)'])
        s=self.process([Line('',t) for t in ['ALINA KIM','Certifications',
            'Certified Cloud Developer','Course covered databases, networks, APIs.']])
        self.assertEqual(len(s['certifications']),1)
        self.assertEqual(s['certifications'][0]['details'],'Course covered databases, networks, APIs.')

    def test_inline_education_credential(self):
        s=self.process([Line('',t) for t in ['ALINA KIM','Education',
            'B.S. in Physics — Northern University (2021) • Certified Research Associate']])
        self.assertEqual(s['certifications'][0]['name']['value'],'Certified Research Associate')
        self.assertEqual(s['education'][0]['institution']['value'],'Northern University')

    def test_mixed_award_section(self):
        s=self.process([Line('',t) for t in ['ALINA KIM','Awards & Certifications',
            '• Cloud Engineering Certification – Northern Academy, Oslo: Completed training.',
            '• Best Innovation Award (2025)']])
        self.assertEqual(s['certifications'][0]['name']['value'],'Cloud Engineering Certification')
        self.assertEqual(s['other_sections'][0]['canonical'],'awards')

    def test_phone_and_portfolio_without_false_email_domain(self):
        s=self.process([Line('',t) for t in ['ALINA KIM',
            '+44-7700900123 | alina@example.org | portfolio.example.design','Summary','Works with Node.js and Python.']])
        self.assertEqual(s['contact']['phones'][0]['value'],'+44-7700900123')
        self.assertEqual([l['value'] for l in s['contact']['links']],['portfolio.example.design'])

    def test_pdf_annotation_destination(self):
        from reportlab.pdfgen.canvas import Canvas
        with TemporaryDirectory() as d:
            p=Path(d)/'links.pdf';c=Canvas(str(p));c.setFont('Helvetica-Bold',20);c.drawString(50,790,'ALINA KIM')
            c.setFont('Helvetica',10);c.drawString(50,765,'Portfolio')
            c.linkURL('https://alina.example.design', (50,760,100,780),relative=0)
            c.drawString(50,735,'Summary');c.drawString(50,715,'Engineer building reliable applications and data tools with a focus on testing quality and clear documentation for teams across many industries.')
            c.save();r=extract(p)
            self.assertEqual(r['quality']['schema_errors'],[])
            self.assertIn('https://alina.example.design',[x['value'] for x in r['structured']['contact']['links']])
