"""Mirror a reviewed local commit into the repo's agent4/ subtree.

No force push, deletion, or writes outside agent4/. The upstream checkout
is ignored locally and preserves the original monorepo history.
"""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT/'.publish'

def git(*args,cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',default='HEAD')
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--message',required=True)
    args=parser.parse_args()
    if git('branch','--show-current',cwd=CHECKOUT).strip()!=b'agent4-Khanh':
        raise SystemExit('Upstream checkout must be on agent4-Khanh.')
    if git('status','--porcelain',cwd=CHECKOUT).strip():
        raise SystemExit('Upstream checkout has pending changes; inspect before publishing.')
    command = ['ls-tree','-r','--name-only','-z',args.commit] if args.all else ['diff-tree','--no-commit-id','--name-only','-r','-z',args.commit]
    files=git(*command).split(b'\0')
    for name in files:
        if not name: continue
        relative=name.decode('utf-8')
        target=(CHECKOUT/'agent4'/relative).resolve()
        if not target.is_relative_to((CHECKOUT/'agent4').resolve()):
            raise SystemExit('Unsafe path in commit.')
        # Deleted files require explicit review; never silently delete upstream.
        content=git('show',f'{args.commit}:{relative}')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
    git('add','--','agent4',cwd=CHECKOUT)
    if not git('diff','--cached','--name-only',cwd=CHECKOUT).strip():
        print('No changes to publish.')
        return
    git('-c','user.name=Codex','-c','user.email=codex@local','commit','-m',args.message,cwd=CHECKOUT)
    subprocess.run(['git','push','origin','agent4-Khanh'],cwd=CHECKOUT,check=True)
    print(git('rev-parse','HEAD',cwd=CHECKOUT).decode().strip())

if __name__=='__main__': main()
