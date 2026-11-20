"""Copy the shared theme into every agent and make sure each agent page links it. Safe to run again.

  python design/sync.py          copy files and add or refresh the link tags
  python design/sync.py --check  only report what is out of date (exit code 1 if anything is)

The links carry a content hash (?v=...) where supported, so a changed theme is never served from a browser cache.
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
    'agent1': dict(
        agent='1', query=True,
        dest='agent1/agent1_service/ui/workspace', url='/workspace-assets/',
        pages=['agent1/agent1_service/ui/workspace/index.html'],
    ),
    'agent2': dict(
        agent='2', query=False,
        dest='agent2/sme_fraud/web', url='assets/',
        pages=[f'agent2/sme_fraud/web/{n}.html' for n in (
            'index', 'workspace', 'bundle-workspace', 'investigation', 'model-management',
            'analysis-settings', 'pipeline-releases', 'label-verification', 'batch-training', 'he-analysis', 'status',
        )],
    ),
    'agent2_legacy': dict(
        agent='2', query=True,
        dest='agent2/review_ui', url='/',
        pages=[f'agent2/review_ui/{n}.html' for n in ('index', 'company_ml', 'data_import', 'ml_reviews', 'p2_controls')],
    ),
    'agent3': dict(
        agent='3', query=True,
        dest='agent3/agent3_tax_compliance/src/assistant/static/assets', url='/assets/',
        pages=['agent3/agent3_tax_compliance/src/assistant/static/index.html',
               'agent3/agent3_tax_compliance/webui/index.html'],
    ),
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


def inject(page: Path, url: str, *, agent: str, use_query: bool):
    if not page.exists():
        return
    text = page.read_bytes().decode('utf-8')
    css = f'{url}platform-theme.css' + (f'?v={version("platform-theme.css")}' if use_query else '')
    js = f'{url}platform-theme.js' + (f'?v={version("platform-theme.js")}' if use_query else '')
    new = text
    if f'data-agent="{agent}"' not in new:
        new = re.sub(r'<html\b(?![^>]*\bdata-agent=)([^>]*)>', rf'<html\1 data-agent="{agent}">', new, count=1, flags=re.IGNORECASE)
    if MARK in new:
        new = re.sub(re.escape(url) + r'platform-theme\.css(\?v=[0-9a-f]+)?', css, new)
        new = re.sub(re.escape(url) + r'platform-theme\.js(\?v=[0-9a-f]+)?', js, new)
    else:
        nl = CRLF if CRLF in new else LF
        i = new.lower().find('</head>')
        if i < 0:
            raise SystemExit(f'{page}: no </head>; add the two tags by hand')
        new = new[:i] + f'<link rel="stylesheet" href="{css}">{nl}<script src="{js}"></script>{nl}' + new[i:]
    nl = CRLF if CRLF in new else LF
    # Product-specific styles load first; shared workspace tokens are authoritative.
    theme_link = re.search(r'[ \t]*<link\b[^>]*href="' + re.escape(css) + r'"[^>]*>[ \t]*(?:\r?\n)?', new)
    if theme_link:
        tag = theme_link.group(0).strip()
        stripped = new[:theme_link.start()] + new[theme_link.end():]
        new = stripped.replace('</head>', tag + nl + '</head>', 1)
        new = re.sub(r'(?:\r?\n[ \t]*){3,}', nl + nl, new)
    if new != text:
        stale.append(str(page.relative_to(ROOT)))
        if not CHECK:
            page.write_bytes(new.encode('utf-8'))


for name, t in TARGETS.items():
    dest = ROOT / t['dest']
    if not dest.exists():
        continue
    for f in ('platform-theme.css', 'platform-theme.js'):
        copy(DESIGN / f, dest / f)
    for font in sorted((DESIGN / 'fonts').glob('*.woff2')):
        copy(font, dest / 'platform-fonts' / font.name)
    for page in t['pages']:
        inject(ROOT / page, t['url'], agent=t['agent'], use_query=t['query'])

print(('Updated:' if (stale and not CHECK) else 'Out of date:' if stale else 'Up to date.') + ''.join(f'\n  {s}' for s in stale))
sys.exit(1 if CHECK and stale else 0)
