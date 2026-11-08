"""Copy the shared theme into every agent and make sure each agent page links it. Safe to run again.

  python design/sync.py          copy files and add or refresh the link tags
  python design/sync.py --check  only report what is out of date (exit code 1 if anything is)

The links carry a content hash (?v=...), so a changed theme is never served from a browser cache.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / 'design'
CHECK = '--check' in sys.argv

# agent folder for the copied files, URL prefix the agent serves that folder under, and the pages that get the tags
TARGETS = {
    'agent1': dict(dest='agent1/agent1_service/ui/workspace', url='/workspace-assets/',
                   pages=['agent1/agent1_service/ui/workspace/index.html']),
    'agent2': dict(dest='agent2/review_ui', url='/',
                   pages=[f'agent2/review_ui/{n}.html' for n in ('index', 'company_ml', 'data_import', 'ml_reviews', 'p2_controls')]),
    'agent3': dict(dest='agent3/agent3_tax_compliance/src/assistant/static/assets', url='/assets/',
                   pages=['agent3/agent3_tax_compliance/src/assistant/static/index.html',
                          'agent3/agent3_tax_compliance/webui/index.html']),
}
MARK = 'platform-theme'
CRLF, LF = chr(13) + chr(10), chr(10)
stale = []


def same(a: Path, b: Path) -> bool:
    return b.exists() and a.read_bytes() == b.read_bytes()


def copy(src: Path, dst: Path):
    if same(src, dst):
        return
    stale.append(str(dst.relative_to(ROOT)))
    if not CHECK:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def version(name: str) -> str:
    return hashlib.sha256((DESIGN / name).read_bytes()).hexdigest()[:8]


def inject(page: Path, url: str):
    text = page.read_bytes().decode('utf-8')
    css = f'{url}platform-theme.css?v={version("platform-theme.css")}'
    js = f'{url}platform-theme.js?v={version("platform-theme.js")}'
    new = text
    if MARK in text:
        new = re.sub(re.escape(url) + r'platform-theme\.css(\?v=[0-9a-f]+)?', css, new)
        new = re.sub(re.escape(url) + r'platform-theme\.js(\?v=[0-9a-f]+)?', js, new)
    else:
        nl = CRLF if CRLF in text else LF
        i = text.lower().find('</head>')
        if i < 0:
            raise SystemExit(f'{page}: no </head>; add the two tags by hand')
        new = text[:i] + f'<link rel="stylesheet" href="{css}">{nl}<script src="{js}"></script>{nl}' + text[i:]
    if new != text:
        stale.append(str(page.relative_to(ROOT)))
        if not CHECK:
            page.write_bytes(new.encode('utf-8'))


for name, t in TARGETS.items():
    dest = ROOT / t['dest']
    for f in ('platform-theme.css', 'platform-theme.js'):
        copy(DESIGN / f, dest / f)
    for font in sorted((DESIGN / 'fonts').glob('*.woff2')):
        copy(font, dest / 'platform-fonts' / font.name)
    for page in t['pages']:
        inject(ROOT / page, t['url'])

print(('Out of date:' if stale else 'Up to date.') + ''.join(f'\n  {s}' for s in stale))
sys.exit(1 if CHECK and stale else 0)
