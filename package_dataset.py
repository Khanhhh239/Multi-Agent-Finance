"""Package only final datasets, source and verified reports, excluding local dependencies."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import argparse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='2')
    args=parser.parse_args()
    root = Path(__file__).resolve().parent
    output = root/"outputs"/f"sme_fraud_v{args.version}.zip"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    files = [root/name for name in ("README.md", "requirements.txt", "requirements-lock.txt", "run_benchmark.ps1", "package_dataset.py")]
    files += sorted((root/"sme_fraud").glob("*.py"))
    files += sorted((root/"tests").glob("*.py"))
    if (root/'review_ui'/'index.html').is_file():
        files += sorted(path for path in (root/'review_ui').glob('*') if path.is_file())
        files += [root/'start_review.py',root/'reports'/'review_ui.md',root/'reports'/'review_ui_validation.json']
    for tag in ("001","003","005"):
        files += sorted((root/"data"/f"sme_fraud_{tag}").glob("*"))
        files += sorted((root/"reports"/f"sme_fraud_{tag}").glob("*"))
    files += [root/"reports"/"summary_vi.md", root/"reports"/"summary.json"]
    files += [root/'reports'/'accounting_review.md',root/'reports'/'accounting_review.json']
    rules_root = root/'reports'/'rules'
    if (rules_root/'summary.json').is_file():
        files += [root/'rule_class_1.md',root/'run_rules_benchmark.ps1',root/'reports'/'rules_implementation.md',
                  rules_root/'summary_vi.md',rules_root/'summary.json']
        # Include reproducible detector outputs; human feedback logs stay local.
        rule_outputs = ('rule_scores.csv','direct_rule_scores.csv','rule_hits.jsonl','rule_config.json',
                        'rule_coverage.json','benford_diagnostics.jsonl','case_queue.csv','case_events.csv',
                        'comparison.json','comparison_scores_test.csv','report_vi.md','validation.json')
        for tag in ('001','003','005'):
            files += [rules_root/f'sme_fraud_{tag}'/name for name in rule_outputs]
    assert all(path.is_file() for path in files), "Missing final deliverable"
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            archive.write(path,path.relative_to(root).as_posix())
    with ZipFile(output) as archive:
        broken = archive.testzip()
        assert broken is None, f"Archive CRC failed: {broken}"
        assert len(archive.namelist())==len(files), "Archive file count"
    print(f"{output}: {len(files)} files, {output.stat().st_size:,} bytes; CRC passed")


if __name__=="__main__":
    main()
