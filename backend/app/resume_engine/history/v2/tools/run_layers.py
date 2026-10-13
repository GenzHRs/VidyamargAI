"""Run each independent layer, save actual output, and return nonzero on failure."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
LAYERS=['ingest','docx','pdf','normalize','classify','sections','fields','validate','pipeline','regressions','layout_fixtures','corpus']

def main() -> int:
    failed=False
    for i,name in enumerate(LAYERS,1):
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',f'test_{i:02d}*','-v'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (ROOT/'reports'/f'layer_{i:02d}_{name}.log').write_text(result.stdout)
        print(f'Layer {i:02d} {name}\n{result.stdout}')
        failed|=result.returncode!=0
    return int(failed)

if __name__=='__main__':raise SystemExit(main())
