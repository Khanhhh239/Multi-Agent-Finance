"""Offline demo UI. Browser timing and entered reviewer names are unverified."""
import json
from pathlib import Path


def render(packet,output):
    assets=Path(__file__).with_name('business_review_assets')
    raw=json.dumps(packet,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html=(assets/'page.html').read_text('utf-8').replace('<!--PACKET-->',raw)
    # One local HTML is portable. No file:// fetch, external server or CDN.
    html=html.replace('/*STYLE*/',(assets/'style.css').read_text('utf-8'))
    html=html.replace('/*APP*/',(assets/'app.js').read_text('utf-8'))
    (output/'BAT_DAU_RÀ_NGHIỆP_VỤ.html').write_text(html,encoding='utf-8')
