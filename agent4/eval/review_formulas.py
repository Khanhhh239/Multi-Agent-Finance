"""Reproduce the accounting review packet: python -m eval.review_formulas."""
import json
from datetime import date
from pathlib import Path
from time import perf_counter
import duckdb
from agent4.engine.engine import ExecutionEngine
from agent4.engine.metrics import REGISTRY
from eval.oracle import oracle

RANGES = [('2026-08-01','2026-08-31'),('2026-10-01','2026-10-31'),('2026-07-01','2026-09-30'),
          ('2025-01-01','2025-12-31'),('2026-01-01','2026-10-14'),('2025-06-15','2025-07-15')]
MUST = {'net_revenue','cogs','gross_profit','operating_expenses','profit_before_tax','net_profit',
        'salary_expense','labor_cost','cash_and_equivalents','ar_balance','ap_balance','inventory_value',
        'tax_payable','current_ratio','net_cash_flow','ar_aging','overdue_receivables','dso','ap_due_soon',
        'upcoming_obligations','expense_spikes','taxable_income'}

def main():
    root = Path(__file__).resolve().parents[1]
    path = root/'data/cfo_warehouse.duckdb'
    engine = ExecutionEngine(path)
    con = duckdb.connect(str(path),read_only=True)
    cells,latencies = [],[]
    for metric,md in REGISTRY.items():
        for start,end in RANGES:
            expected = oracle(con,metric,date.fromisoformat(start),date.fromisoformat(end),md.default_view)
            t = perf_counter()
            actual = engine.query(metric,{'start_date':start,'end_date':end})['value']
            latencies.append((perf_counter()-t)*1000)
            tolerance = .5 if md.unit=='VND' else 1e-9
            ok = actual is None and expected is None or actual is not None and expected is not None and abs(actual-expected)<=tolerance
            cells.append(dict(metric=metric,start=start,end=end,view=md.default_view,engine=actual,oracle=expected,passed=ok))
    report = {'measured_on':'2026-10-16','seed':engine.info.get('seed'),'data_version':engine.info.get('data_version','unversioned'),
              'gl_rows':con.execute('SELECT COUNT(*) FROM gl_entry').fetchone()[0],
              'cells':len(cells),'passed':sum(c['passed'] for c in cells),
              'query_p95_ms':sorted(latencies)[int(len(latencies)*.95)],'results':cells}
    destination = root/'docs/5_handoff/measurements'
    destination.mkdir(exist_ok=True)
    (destination/'g0_golden.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# Rà soát công thức — kết quả kỹ thuật và hồ sơ T0.6','',
             'Ngày đo: 16/10/2026. Dữ liệu tổng hợp seed 20251; không phải xác nhận tính đúng pháp lý hay phê duyệt kế toán.',
             f"Oracle độc lập: **{report['passed']}/{report['cells']}** ô, 66 chỉ số × 6 kỳ. Oracle đọc bảng gốc, không import engine.",
             f"p95 truy vấn trong lượt đối chiếu: {report['query_p95_ms']:.2f} ms trên {report['gl_rows']:,} dòng; chưa đại diện tải đồng thời.",
             '', '**G0.7: CHỜ DUYỆT.** Người duyệt: ______. Chức danh: ______. Ngày: ______. Chữ ký/xác nhận: ______.',
             '', 'Các kỳ: tháng khóa 08/2026; tháng dở dang 10/2026; Q3/2026; năm 2025; YTD; 15/06–15/07/2025.',
             '', '| Ưu tiên | Chỉ số | Nhãn | Công thức | Engine Q3 | Oracle Q3 | Đối chiếu | Câu hỏi kế toán | Duyệt |',
             '|---|---|---|---|---:|---:|---|---|---|']
    questions = {
        'dso':'Xác nhận doanh số bán chịu gồm VAT, bình quân dư đầu/cuối và cách xử lý mẫu số 0.',
        'dso_actual':'Xác nhận ngày ghi sổ hoặc ngày tiền về; mặc định receipt; bỏ khách lẻ RET.',
        'equity':'Xác nhận gồm kết quả chưa kết chuyển loại 5–9.',
        'tax_payable':'Khung mặc định tax có phù hợp với số dư nghĩa vụ pháp lý?',
        'expense_spikes':'Bình quân 3 tháng so với tổng kỳ nhiều tháng có ý nghĩa? Hiện giữ định nghĩa cũ.',
        'upcoming_obligations':'Xác nhận ước tính lương/lãi và các nghĩa vụ quá hạn; đây là dự báo.',
        'cit_estimate':'20% là giả định mô phỏng; xác nhận ưu đãi/lỗ chuyển kỳ trước dùng thật.',
        'payroll_summary':'Bảng lương theo tháng đầy đủ khi truy vấn cắt giữa tháng: cần chốt ngữ nghĩa.',
        'revenue_deductions':'Xác nhận Nợ 511 TT133 + net Nợ 521 TT200.',
        'cash_flow_breakdown':'Một chứng từ nhiều tài khoản đối ứng hiện được phân vào một nhóm ưu tiên: cần xác nhận.',
    }
    for metric,md in REGISTRY.items():
        c = next(c for c in cells if c['metric']==metric and c['start']=='2026-07-01')
        lines.append(f"| {'**Must**' if metric in MUST else ''} | `{metric}` | {md.label} | {md.formula.replace('|','/')} | {c['engine']} | {c['oracle']} | {'KHỚP' if c['passed'] else 'LỆCH'} | {questions.get(metric,'Xác nhận công thức, dấu và khung trong định nghĩa.')} | CHỜ |")
    lines += ['', '## Ngoại lệ và giới hạn cần giữ minh bạch','',
              '- A4: chứng từ lệch Nợ/Có 500.000 đồng ngày 31/07/2026 là hard case có chủ đích. Phương trình kế toán nguyên trạng lệch đúng khoản này sau ngày đó; test đối chiếu và tách ngoại lệ, không sửa dữ liệu để làm xanh.',
              '- Ngân sách dùng random() DuckDB không seed trong bản dữ liệu cũ; tái lập sổ cái được kiểm chứng riêng, không tuyên bố toàn kho tái lập.',
              '- Các kết quả này kiểm chứng hiện thực so với định nghĩa; chưa thay thế phê duyệt độc lập của kế toán.',
              '- P1/P2 chưa chạy vì handoff yêu cầu qua G0 trước. Không dùng seed val/test hay chạy Qwen để báo thành tích khi G0 chưa được duyệt.']
    (root/'docs/5_handoff/FORMULA_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    engine.close()
    con.close()
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
    if report['passed'] != report['cells']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
