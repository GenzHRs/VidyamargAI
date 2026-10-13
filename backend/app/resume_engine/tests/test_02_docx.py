from pathlib import Path
from zipfile import ZipFile
import tempfile
import unittest
from resume_extract.docx_reader import read_docx
from resume_extract.config import load_config

class DocxTests(unittest.TestCase):
    def test_xml_order_wrappers_and_real_cells(self):
        body='''<w:p><w:r><w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="FFFFFF"/><w:caps/></w:rPr><w:t>Ada</w:t></w:r><w:hyperlink><w:r><w:t> link</w:t></w:r></w:hyperlink><w:r><w:br/><w:t>City, ST</w:t><w:tab/><w:t>ZIP</w:t></w:r></w:p>
        <w:sdt><w:sdtContent><w:p><w:r><w:t>Contact</w:t></w:r></w:p></w:sdtContent></w:sdt>
        <w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>Merged once</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nested</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>
        <w:p><w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>Text box</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r></w:p>
        <w:p><w:r><w:t>After table</w:t></w:r></w:p>'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.docx'
            with ZipFile(p,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
                z.writestr('word/header1.xml','<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Header Name</w:t></w:r></w:p></w:hdr>')
            doc=read_docx(p,load_config())
        self.assertEqual([x.text for x in doc.lines],['Header Name','Ada link','City, ST\tZIP','Contact','Merged once','Nested','Text box','After table'])
        self.assertEqual(doc.lines[1].runs[0].size,16)
        self.assertTrue(doc.lines[1].runs[0].caps)
        self.assertEqual(doc.lines[1].runs[0].color,'FFFFFF')
        self.assertEqual(doc.raw_text.count('Merged once'),1)
