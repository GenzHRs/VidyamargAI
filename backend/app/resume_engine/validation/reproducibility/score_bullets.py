"""Separate full-text comparison for reviewed job bullets (not just counts)."""
from pathlib import Path
import argparse,json,re,unicodedata
ROOT=Path(__file__).resolve().parents[1]

def norm(text):
    return ' '.join(re.sub(r'^[•–−*-]\s*','',unicodedata.normalize('NFKC',text).strip()).split())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions',type=Path,default=ROOT.parent/'results')
    args=parser.parse_args()
    gold=json.loads((ROOT/'audit/source_job_bullets.json').read_text())
    expected=actual=matched=0;failures=[]
    for rid,jobs in sorted(gold.items()):
        pred=json.loads((args.predictions/rid/'structured.json').read_text())['experience']
        actual+=sum(len(j['bullets']) for j in pred)
        for ji,bullets in enumerate(jobs):
            for bi,text in enumerate(bullets):
                expected+=1
                value=pred[ji]['bullets'][bi] if ji<len(pred) and bi<len(pred[ji]['bullets']) else ''
                if norm(text)==norm(value):matched+=1
                else:failures.append({'resume':rid,'job_index':ji,'bullet_index':bi,'expected':text,'actual':value})
    report={'expected':expected,'actual':actual,'exact_matches':matched,
            'recall':matched/expected,'precision':matched/actual if actual else 0,'failures':failures,
            'methodology':'Full bullet strings, fixed job/bullet ordinals; NFKC, whitespace and leading bullet marker normalization only. References copied from the completed source-reviewed audit before v3. Development set; not independent validation.'}
    (ROOT/'audit/bullet_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if matched==expected==actual else 1

if __name__=='__main__':raise SystemExit(main())
