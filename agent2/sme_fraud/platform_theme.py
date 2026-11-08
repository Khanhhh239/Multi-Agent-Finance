"""Static routes for the shared platform theme (design/platform-theme.css and the bundled font files)."""
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[1] / 'review_ui'


def theme_assets():
    fonts = sorted((WEB_ROOT / 'platform-fonts').glob('*.woff2'))
    return {'/platform-theme.css': ('platform-theme.css', 'text/css; charset=utf-8'),
            '/platform-theme.js': ('platform-theme.js', 'text/javascript; charset=utf-8'),
            **{f'/platform-fonts/{f.name}': (f'platform-fonts/{f.name}', 'font/woff2') for f in fonts}}
