"""Đồng bộ số v2 từ CSV vào index, ghi ngày và giới hạn dữ liệu."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]


def main():
    frame=pd.read_csv(ROOT/'outputs/t1/real_v2/C_real_v2.csv')
    selected=frame[frame.model.str.startswith('BLEND(DH-GBM,B1d) w=')].set_index('setting')
    state=ROOT/'outputs/implementation/fullweek_refresh.json'
    completed=False
    if state.exists():
        from fullweek_refresh import JOBS
        latest={row['job']:row for row in json.loads(state.read_text(encoding='utf-8'))}
        completed=all(latest.get(name,{}).get('status')=='passed' for name in JOBS)
    lines=[]
    for name,label in [('ci','Customer Invoices'),('bpi','BPI')]:
        row=selected.loc[name]
        lines.append(f"{label}: giảm pinball {row.improvement_vs_B1d_pct:.1f}% [{row.improvement_ci_low:.1f}; {row.improvement_ci_high:.1f}] so với B1d")
    status='Chuỗi 18 job hazard/E2E đã chạy lại với hậu tố `-fullweek`; số v1 giữ để kiểm toán.' if completed else 'Các kết quả hazard tổng hợp/E2E trước 20/10 đang chờ chạy lại với hậu tố `-fullweek`.'
    statement='- T1 dữ liệu thật — **giao thức v2, cập nhật 21/10/2026**: BLEND(DH-GBM,B1d), w chọn trên cửa sổ hiệu chỉnh rồi refit; '+ '; '.join(lines)+'.\n  Đây là bằng chứng phương pháp trên hai bộ thật, chưa đại diện SME Việt Nam. '+status+'\n'
    path=ROOT/'docs/00_INDEX.md';text=path.read_text(encoding='utf-8')
    start=text.index('- T1 ');end=text.index('- T4:',start)
    text=text[:start]+statement+text[end:]
    if completed:
        text=text.replace('Các số hazard tổng\n> hợp/E2E trước sửa `expand` đang được chạy lại;',
            'Chuỗi hazard tổng\n> hợp/E2E sau sửa `expand` đã chạy lại;')
    for prefix,next_prefix,replacement in [
        ('- T7:','- T9:','- T7: có phát hiện thay đổi theo khách/danh mục và phép đo chuyển chế độ; kết quả và giới hạn ở bảng hiện hành.\n'),
        ('- T9:','- T0/T5:','- T9: khớp sao kê lai quy tắc/ML, phần mơ hồ vào hàng chờ; xem G15 và đường precision–coverage chọn trên nguồn.\n'),
        ('- Thích nghi miền:','- T2:','- Thích nghi miền/T8: xem kết quả và CI của chuỗi fullweek; các giả thuyết chưa đạt giữ nguyên tiêu chí đăng ký.\n'),
        ('- T2:','**Chưa xong','- T2: có các biến thể SBA EXEMPT và hiệu chỉnh xác suất; bằng chứng cho vay Mỹ giữ phạm vi phương pháp.\n\n')]:
        if prefix in text and next_prefix in text:
            begin=text.index(prefix);end=text.index(next_prefix,begin);text=text[:begin]+replacement+text[end:]
    if '- T6:' in text and '- Thích nghi miền' in text:
        begin=text.index('- T6:');end=text.index('- Thích nghi miền',begin)
        text=text[:begin]+'- T6: E2E XML/CSV, nhãn T9 ước lượng, khoảng số dư và cảnh báo; số đo hiện hành ở G12/G13 và CSV fullweek, đối chứng bổ sung được báo riêng.\n'+text[end:]
    if '**Chưa xong' in text and '**Kinh tế.' in text:
        begin=text.index('**Chưa xong');end=text.index('**Kinh tế.',begin)
        text=text[:begin]+'**Trạng thái nghiệm thu:** xem cổng hiện hành và nhật ký Sprint 1. API/dashboard/T10/giám sát local đã có; chuyên gia, UAT và pilot thật vẫn cần bằng chứng ngoài mô phỏng.\n\n'+text[end:]
    path.write_text(text,encoding='utf-8');print('updated index from v2 CSV')


if __name__=='__main__':main()
