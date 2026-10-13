"""Fresh extraction of the fixed audit corpus; labels are never input to the engine."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from resume_extract.pipeline import extract, write_outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=ROOT/'inputs')
    parser.add_argument('--out',type=Path,default=ROOT.parent/'results')
    args=parser.parse_args();seen={}
    manifest=json.loads((ROOT/'audit/manifest.json').read_text())
    for item in manifest:
        path=args.inputs/item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Source bytes changed: '+item['id'])
        result=extract(path,seen=seen)
        write_outputs(result,args.out/item['id'])
        print(item['id'],item['file'],result['quality']['completeness']['status'],flush=True)
    for script,extra in [('score_audit.py',['--min-f1','0.95']),('score_bullets.py',[])]:
        subprocess.run([sys.executable,str(Path(__file__).with_name(script)),
                        '--predictions',str(args.out),*extra],check=True)


if __name__=='__main__':main()
