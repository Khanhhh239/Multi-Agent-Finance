"""Real Chrome/HTTP; synthetic invoice and reader double, isolated storage."""
import json
import re
import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/recovery'))
sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from test_regions import RegionTests
from src.app import create_app


def main():
    case=RegionTests('test_reread_is_cached_candidate_with_original_and_transform');case.setUp();f=case.f
    out=APP/'data/region_recovery/browser';out.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(f.fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);checks=[];errors=[];posts=[]
    try:
        with patch('src.recovery.api.RegionRecovery',return_value=case.service),sync_playwright() as pw:
            thread.start()
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' and '/reread-region?' in r.url else None)
            page.goto(f'http://127.0.0.1:{port}/review')
            page.locator('#token').fill(f.fixture.token);page.locator('#payer').fill(f.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+f.record.record_id+'"]').click()
            expect(page.locator('#page-image')).to_be_visible()
            (out/'opened.html').write_bytes(page.content().encode())
            page.screenshot(path=str(out/'opened.png'),full_page=True)
            page.get_by_role('button',name='Chi tiết dòng 1',exact=True).click()
            source=page.locator('.items-table .field').first
            source.get_by_role('button',name='Xem nguồn',exact=True).click()
            expect(page.locator('#reread-region')).to_be_visible()
            before=f.repo.base.record(f.ctx,f.payer,f.record.record_id)
            page.locator('#reread-region').click()
            expect(page.locator('#region-output')).to_contain_text('New observed text',timeout=20000)
            assert f.repo.base.record(f.ctx,f.payer,f.record.record_id)==before
            assert not page.locator('#items-complete').is_checked()
            checks.append('Reread shows a separate candidate and original value without changing CFR or completeness')
            page.locator('#reread-region').click()
            expect(page.locator('#reread-region')).to_be_enabled(timeout=15000)
            assert case.reader.calls==1
            checks.append('Repeated HTTP reread uses the pinned cache without another model call')
            page.get_by_role('button',name='Đưa vào bản nháp',exact=True).click()
            expect(page.locator('.items-table textarea').first).to_have_value(re.compile('New observed text'))
            assert f.repo.base.record(f.ctx,f.payer,f.record.record_id)==before
            before_posts=len(posts);page.locator('#reread-region').click()
            expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp')
            assert len(posts)==before_posts
            checks.append('Using a candidate creates only a draft; draft blocks another model request')
            page.locator('#save').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 2',timeout=15000)
            assert f.repo.base.record(f.ctx,f.payer,f.record.record_id).items[0].description.confidence_basis=='HUMAN_CONFIRMED'
            checks.append('Explicit reviewed save creates a new revision through the existing correction service')
            page.get_by_role('button',name='Chi tiết dòng 1',exact=True).click()
            source=page.locator('.items-table .field').first
            source.get_by_role('button',name='Xem nguồn',exact=True).click()
            held=[];pattern='**/reread-region?*'
            page.route(pattern,lambda route:held.append(route));page.locator('#reread-region').click()
            expect(page.locator('#reread-region')).to_be_disabled()
            assert held
            other=page.locator('.field').filter(has=page.get_by_label('MST người bán',exact=True))
            other.get_by_role('button',name='Xem nguồn',exact=True).click()
            held[0].continue_();page.unroute(pattern)
            expect(page.locator('#reread-region')).to_be_hidden()
            checks.append('Switching to another field hides the feature and fences a late response')
            # XSS strings are displayed literally. No HTML is created from OCR.
            case.reader.text='<img src=x onerror=alert(1)>'
            source.get_by_role('button',name='Xem nguồn',exact=True).click()
            # The held request populated this revision cache; isolate a runtime change.
            with patch.object(case.reader,'inventory',return_value={'runtime_sha256':'d'*64}):
                page.locator('#reread-region').click()
                expect(page.locator('#region-output')).to_contain_text('<img src=x',timeout=20000)
            assert page.locator('#region-output img').count()==0
            checks.append('Untrusted recognition text remains text and cannot create HTML')
            for width in (390,1440):
                page.set_viewport_size({'width':width,'height':1000})
                page.screenshot(path=str(out/f'width-{width}.png'),full_page=True)
                overflow=page.evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,cl:e.className,right:e.getBoundingClientRect().right})).slice(0,20)')
                (out/f'overflow-{width}.json').write_bytes(json.dumps(overflow,ensure_ascii=False,indent=2).encode())
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            checks.append('Region controls fit desktop and mobile without horizontal page overflow')
            assert not errors,errors;browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        case.doCleanups()
    result={'result':'PASS','checks':checks,'page_errors':errors,'scope':'Synthetic data, reader double; real Chrome/HTTP/correction storage, no OCR accuracy claim'}
    (out/'result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
