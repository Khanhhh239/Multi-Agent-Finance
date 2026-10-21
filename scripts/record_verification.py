"""Gom kiểm chứng thành CSV, số lấy từ JUnit/stdout chứ không ghi tay."""
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT


def main():
    rows=[];xml=OUT/'implementation/tests.xml'
    if xml.exists():
        suites=list(ET.parse(xml).getroot().iter('testsuite'))
        rows.append(dict(environment='workspace_venv',tests=sum(int(s.get('tests','0')) for s in suites),
                         failures=sum(int(s.get('failures','0'))+int(s.get('errors','0')) for s in suites),
                         skipped=sum(int(s.get('skipped','0')) for s in suites),evidence=str(xml.relative_to(OUT))))
    clean_xml=OUT/'implementation/tests_clean.xml'
    clean=OUT/'clean_environment_tests.log'
    if clean_xml.exists():
        suites=list(ET.parse(clean_xml).getroot().iter('testsuite'))
        rows.append(dict(environment='fresh_venv_from_requirements',tests=sum(int(s.get('tests','0')) for s in suites),
                         failures=sum(int(s.get('failures','0'))+int(s.get('errors','0')) for s in suites),
                         skipped=sum(int(s.get('skipped','0')) for s in suites),evidence=str(clean_xml.relative_to(OUT))))
    elif clean.exists():
        text=clean.read_text(encoding='utf-8',errors='replace')
        matched=re.search(r'(\d+) passed',text)
        failed=re.search(r'(\d+) failed',text)
        if matched:rows.append(dict(environment='fresh_venv_from_requirements',tests=int(matched[1]),
                                 failures=int(failed[1]) if failed else 0,skipped=0,evidence=str(clean.relative_to(OUT))))
    pd.DataFrame(rows).to_csv(OUT/'implementation/test_summary.csv',index=False)


if __name__=='__main__':main()
