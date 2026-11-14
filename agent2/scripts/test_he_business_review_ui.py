"""Offline review rehearsal in isolated Chrome; fixture entries are not human reviews."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.he_inference.business_review import validate_feedback,summarize
from experiments.he_inference.protocol import read_json


def run(packet_dir,output):
    from playwright.sync_api import sync_playwright,expect
    packet=read_json(packet_dir/'packet.json');output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    with tempfile.TemporaryDirectory(prefix='review-ui-fixtures-') as temporary, sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport=dict(width=1440,height=1100),accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        url=(packet_dir/'BAT_DAU_RÀ_NGHIỆP_VỤ.html').resolve().as_uri();page.goto(url)
        expect(page.locator('#overall')).to_contain_text('0/10');expect(page.locator('#cases button')).to_have_count(5)
        assert page.locator('#summary tr').count()==3
        passed('blank demo has ten unreviewed cases, five per company, no fabricated usefulness')
        page.screenshot(path=str(output/'01-blank.png'),full_page=False)
        # A stale second tab must not erase the unrelated result submitted below.
        second=context.new_page();second.on('pageerror',lambda e:errors.append(str(e)));second.goto(url)
        page.bring_to_front();page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('Điền tên')
        expect(page.locator('#overall')).to_contain_text('0/10');passed('cannot submit an empty review')

        def fill(target,name,useful='not_assessed',action=True):
            target.bring_to_front();target.locator('#reviewer').fill(name);target.locator('#start').click()
            target.wait_for_timeout(60)
            target.locator('#evidence input').first.check();target.locator('#resolution').select_option('inconclusive')
            target.locator('#explanation').fill('FIXTURE kiểm thử: chỉ có bản ghi mô phỏng, chưa có chứng từ gốc.')
            target.locator('#missing').fill('FIXTURE: thiếu phê duyệt chi và chứng từ chuyển tiền.')
            target.locator('#usefulness').select_option(useful)
            if action:target.locator('#action').fill('FIXTURE: đề nghị kế toán bổ sung phê duyệt và chứng từ để rà tiếp.')

        fill(page,'Người rà FIXTURE 1','yes',False)
        page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('hữu ích cần nêu rõ')
        passed('usefulness yes cannot be recorded without a concrete action')
        page.locator('#action').fill('FIXTURE: đề nghị kế toán bổ sung phê duyệt và chứng từ.')
        page.locator('#save').click();expect(page.locator('#overall')).to_contain_text('1/10')
        expect(page.locator('#start')).to_be_disabled();passed('inconclusive and useful can be recorded independently, with active browser time')

        second.bring_to_front();second.locator('#company').select_option('C002')
        fill(second,'Người rà FIXTURE 2');second.locator('#save').click()
        expect(second.locator('#overall')).to_contain_text('2/10')
        passed('saving C002 in a stale second tab preserves the existing C001 review')
        page.bring_to_front();page.reload();expect(page.locator('#overall')).to_contain_text('2/10')
        expect(page.locator('#saved-info')).to_contain_text('phiên bản 1')
        passed('reload restores results and keeps a submitted review locked until explicit revision')

        page.locator('#revise').click();page.locator('#start').click();page.wait_for_timeout(80);page.locator('#pause').click()
        def draft_ms():
            return page.evaluate('''()=>{const p=JSON.parse(document.getElementById('packet').textContent);return JSON.parse(localStorage.getItem('agent2.business-demo.'+p.packet_id)).drafts[p.cases[0].case_id].active_ms;}''')
        elapsed=draft_ms();assert elapsed>0
        page.wait_for_timeout(120);assert draft_ms()==elapsed
        page.reload();assert draft_ms()==elapsed
        passed('pause and reload do not count idle time as active review time')
        page.locator('#usefulness').select_option('no');page.locator('#explanation').fill('FIXTURE phiên bản 2: thử sửa đánh giá lợi ích, vẫn chưa đủ chứng từ.')
        page.locator('#save').click();expect(page.locator('#saved-info')).to_contain_text('phiên bản 2')
        expect(page.locator('#overall')).to_contain_text('2/10')
        passed('editing appends revision 2 and keeps revision 1 without counting a new case')
        with page.expect_download() as download:page.locator('#export').click()
        path=Path(temporary)/'feedback.fixture.json';download.value.save_as(path)
        feedback=read_json(path);history=validate_feedback(packet,feedback);summary=summarize(packet,feedback)
        assert len(feedback['reviews'])==3 and len(history)==2
        assert sum(c['reviewed'] for c in summary['companies'])==2
        assert summary['companies'][0]['declared_not_useful']==1
        assert summary['companies'][1]['usefulness_not_assessed']==1
        assert not summary['training_eligible'] and not summary['business_effectiveness_verified']
        assert all(not c['timing_verified'] for c in summary['companies'])
        passed('export validates against the locked packet; keeps history, unknown usefulness and unverified timing')
        assert not errors,errors;passed('no JavaScript errors')
        context.close();browser.close()
    report=dict(status='passed',count=len(checks),checks=checks,browser_errors=errors,
        data='isolated browser test fixtures only',human_business_reviews_created=False,
        real_packet_feedback_unchanged=True,live_services_changed=False)
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packet-dir',required=True,type=Path);parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();run(args.packet_dir.resolve(),args.output_dir.resolve())
