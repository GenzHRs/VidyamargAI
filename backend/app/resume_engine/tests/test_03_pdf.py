import unittest
from resume_extract.pdf_reader import xy_cut,word_lines
from resume_extract.config import load_config

class PdfTests(unittest.TestCase):
    def test_hero_and_independent_columns(self):
        c=load_config();items=[dict(text='HERO',x0=10,x1=400,top=0,bottom=15)]
        for x,label in [(10,'L'),(220,'R')]:
            for y in [40,60,80,100]:items.append(dict(text=label,x0=x,x1=x+100,top=y,bottom=y+10))
        order=[w['text'] for _,r in xy_cut(items,c['pdf']) for w in sorted(r,key=lambda w:w['top'])]
        self.assertEqual(order,['HERO']+['L']*4+['R']*4)
    def test_word_count_and_style(self):
        c=load_config();words=[dict(text='White',x0=0,x1=20,top=0,bottom=10,size=10,fontname='Bold',non_stroking_color=(1,1,1)),dict(text='text',x0=25,x1=40,top=0,bottom=10,size=10,fontname='Regular')]
        lines=word_lines(words,c,{'flow':'test'})
        self.assertEqual(lines[0].text,'White text');self.assertTrue(lines[0].bold)
