"""Create isolated JSON source packages and separate expected outcomes for 35 rules."""
import argparse,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sme_fraud.rules import RULE_NAMES
from sme_fraud.native_rule_demo import scenario,statistical_scenario
from sme_fraud.native_rule_node import validate_bundle
from sme_fraud.import_files import canonical,digest
from finance_input import AccessScope


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);cases=[]
    for company in ('C001','C002'):
        scope=AccessScope('native-demo',frozenset({company}),'synthetic-producer',frozenset({'data.import'}))
        for code in [r for r in RULE_NAMES if not r.startswith('D')]+['D_GROUP']:
            for positive in (True,False):
                bundle,expected=statistical_scenario(positive,company) if code=='D_GROUP' else scenario(code,positive,company)
                report=validate_bundle(bundle,scope)
                if report['status']!='accepted':raise ValueError(report['errors'][:5])
                case_id=company+'_'+code+('_signal' if positive else '_control')
                payload=canonical(bundle);name=case_id+'.source.json';(output/name).write_bytes(payload)
                cases.append(dict(case_id=case_id,company_id=company,source_file=name,source_sha256=digest(payload),expected=expected))
    manifest=dict(version='native-rule-demo/1.0.0',synthetic_only=True,rule_ids=list(RULE_NAMES),cases=cases,expectations_are_outside_source=True,cloud_or_portal_changed=False)
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    instructions='# Bộ dữ liệu kiểm chứng 35 luật tại node doanh nghiệp\n\n120 gói nguồn JSON cho C001/C002. Kết quả kỳ vọng ở manifest.json, không nằm trong nguồn tính luật. Nhóm D dùng gói 3.001 giao dịch; các luật còn lại có ca trúng và đối chứng riêng.\n\nĐây là profile `native-rule-source/1.0.0` cho kiểm chứng local; chưa tải trực tiếp vào màn hình nhập snapshot 1.1.0 hoặc cloud HE.\n\nChạy từ thư mục dự án:\n\n```powershell\n& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_native_rule_demo.py --input-dir '+str(output).replace('\\','/')+' --output-dir .runtime/native-rule-results-new\n```\n\nMở REPORT.md trong thư mục kết quả. Dữ liệu và phê duyệt đều mô phỏng, chưa chứng minh độ chính xác trên doanh nghiệp thật.\n'
    (output/'README.md').write_text(instructions,encoding='utf-8')
    archive=output.with_suffix('.zip')
    if archive.exists():raise ValueError('Archive already exists')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in sorted(output.iterdir()):z.write(file,file.name)
    result=dict(status='prepared',companies=2,source_packages=len(cases),expected_rule_checks=140,source_directory=str(output),zip_file=str(archive),zip_bytes=archive.stat().st_size)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();prepare(a.output_dir.resolve())
