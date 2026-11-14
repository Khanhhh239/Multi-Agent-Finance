"""Local, offline Vietnamese tables for a synthetic HE comparison run."""
from html import escape

MODES=dict(disconnect_before_claim='Mất worker trước khi nhận phép tính',
    controlled_restart_during_compute='Khởi động lại có chờ hoàn tất phép tính',
    hard_crash_during_compute='Worker chết giữa phép tính, chưa lưu kết quả')


def render(report,output):
    text=['# Đối chiếu chấm rõ và chấm mã hóa','',
        '**Kết quả đo: '+report['status'].upper()+'**. Dùng cùng model, snapshot, feature và thời điểm nguồn của từng doanh nghiệp.','',
        '| Doanh nghiệp | Số GD | Lượt đo | Sai số lớn nhất | Cùng thứ tự mọi lượt | Cặp đảo thứ tự đáng kể | Chấm rõ p50 (ms) | HE p50 (ms) | HE p95 (ms) |',
        '|---|---:|---:|---:|---|---:|---:|---:|---:|']
    main=[];details=[];detail_text=[]
    for c in report['companies']:
        values=[c['company_id'],c['row_count'],c['repetitions'],f"{c['maximum_absolute_error']:.3e}",
            'Có' if c['exact_order_equal_all_trials'] else 'Không',c['material_pair_inversions'],
            f"{c['plaintext_pipeline']['median_ms']:.2f}",f"{c['he_pipeline']['median_ms']:.2f}",f"{c['he_pipeline']['p95_ms']:.2f}"]
        main.append(values);text.append('| '+' | '.join(map(str,values))+' |')
        m=c['trials'][0]['metrics']
        detail_text.extend(['','## '+c['company_id'], '',
            'Model: `'+c['artifact_id']+'`. Snapshot: `'+c['snapshot_id']+'`. `as_of`: '+c['as_of']+'.','',
            f"Ngưỡng sai số: |HE − rõ| ≤ {m['absolute_tolerance']} + {m['relative_tolerance']} × |điểm rõ|. Tất cả lượt đạt: {'có' if c['all_scores_within_tolerance'] else 'không'}.",'',
            '| Mã GD | Điểm rõ | Điểm HE (lượt 1) | Sai số tuyệt đối | Hạng rõ | Hạng HE |',
            '|---|---:|---:|---:|---:|---:|'])
        rr=[]
        for row in m['rows']:
            v=[row['record_id'],f"{row['plaintext_score']:.9f}",f"{row['encrypted_score']:.9f}",
                f"{row['absolute_error']:.3e}",row['plaintext_rank'],row['encrypted_rank']]
            detail_text.append('| '+' | '.join(map(str,v))+' |');rr.append(v)
        detail_text.extend(['', 'Thứ tự từ đáng kiểm tra nhất (rõ): '+ ' → '.join(r[0] for r in m['plaintext_order'])+'.',
            'Thứ tự từ đáng kiểm tra nhất (HE): '+ ' → '.join(r[0] for r in m['encrypted_order'])+'.',
            f"Spearman lượt đầu: {m['spearman']}. Top-{m['top_k']} trùng {m['top_k_overlap']}/{m['top_k']}; top-k gồm toàn bộ mẫu: {m['top_k_covers_entire_dataset']}."])
        details.append((c['company_id'],rr))
    text.extend(detail_text)
    text.extend(['','## Khôi phục','',
        '| Loại sự cố | Thành công / lần ngắt xác nhận | Lần ngắt chưa xác nhận | Tỷ lệ quan sát | Thời gian khôi phục p50 (ms) |',
        '|---|---:|---:|---:|---:|'])
    recovery=[]
    for g in report['recovery_summary']:
        rate='Chưa đủ dữ liệu' if g['success_fraction'] is None else f"{g['success_fraction']*100:.0f}%"
        ms='—' if g['successful_recovery_time'] is None else f"{g['successful_recovery_time']['median_ms']:.2f}"
        values=[MODES[g['mode']],f"{g['successful']}/{g['confirmed']}",g['inconclusive'],rate,ms]
        recovery.append(values);text.append('| '+' | '.join(map(str,values))+' |')
    text.extend(['','Không gộp các loại sự cố thành một tỷ lệ chung. Hai doanh nghiệp cho hai ca mặc định mỗi loại; chưa đủ để ước lượng độ tin cậy vận hành.','',
        '## Cách đo','',
        '- Chấm rõ: kiểm scope, đọc/kiểm model, tạo feature từ snapshot, chuẩn hóa và tính điểm.',
        '- Chấm HE: từ submit tới kết quả đã giải mã/lưu tại DN; gồm kiểm worker, đọc model/feature, mã hóa, checkpoint, HTTP worker và polling.',
        '- Mỗi DN chạy một lượt làm nóng rồi đo '+str(report['measurement']['repetitions'])+' lượt mới; đổi thứ tự chạy rõ/HE xen kẽ. Không lấy cache làm số đo lượt chấm mới.',
        '- Timing bình thường không gồm khởi động dịch vụ, fit hoặc Portal/trình duyệt. Timing khôi phục có khởi động lại worker/node.',
        '- Khởi động lại có kiểm soát dùng Jobs.close chờ phép tính xong rồi mở lại cùng state. Ca bấm nút Portal đã có bằng chứng riêng ở lượt nghiệm thu trước.',
        '- Điểm và thứ tự đối chiếu theo mã giao dịch + revision trong đúng DN. Cặp có khoảng cách nhỏ hơn ngân sách sai số không tính là đảo hạng đáng kể.','',
        '## Giới hạn','',
        '- Dữ liệu mô phỏng, Mahalanobis hai feature; không phải tỷ lệ phát hiện đúng sai phạm.',
        '- Top-5 trên 5 giao dịch luôn bao phủ toàn bộ, không chứng minh ML chọn thêm giao dịch hữu ích.',
        '- Chỉ đo loopback. p95 từ số lượt nhỏ là mô tả mẫu, chưa phải cam kết thời gian cloud.',
        '- Khôi phục chỉ với cùng request đã khóa, trong TTL và còn đủ state. Không đổi nonce hoặc tự chấm rõ để che lỗi.',
        '- Model, snapshot nguồn và khóa giữ nguyên. Không thay cấu hình hoặc dừng dịch vụ live.','',
        '[Dữ liệu đầy đủ từng lượt, thời gian và ca sự cố](comparison.json).'])
    (output/'REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')

    def table(headers,rows):
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    body='<h1>Đối chiếu chấm rõ và chấm mã hóa</h1><p class="note">Dữ liệu mô phỏng · C001/C002 · Cùng model và snapshot · '+escape(report['status'].upper())+'</p>'
    body+='<p>Kiểm chứng phép tính mã hóa giữ đúng điểm và thứ tự. Kết quả này chưa đánh giá độ chính xác phát hiện sai phạm.</p>'
    body+=table(['DN','Số GD','Lượt đo','Sai số lớn nhất','Cùng thứ tự mọi lượt','Cặp đảo đáng kể','Rõ p50 (ms)','HE p50 (ms)','HE p95 (ms)'],main)
    body+='<h2>Khôi phục theo loại sự cố</h2>'+table(['Loại sự cố','Thành công / ca xác nhận','Ca chưa xác nhận','Tỷ lệ quan sát','Khôi phục p50 (ms)'],recovery)
    body+='<p class="note">Không gộp các loại sự cố thành một tỷ lệ. Đọc đúng số ca thành công/thất bại trong bảng; khôi phục chỉ trong TTL và còn nguyên state. Số ca nhỏ, chưa phải SLA.</p>'
    for company,rows in details:
        body+='<h2>'+escape(company)+' — điểm và thứ tự lượt đầu</h2>'+table(['Mã GD','Điểm rõ','Điểm HE','Sai số','Hạng rõ','Hạng HE'],rows)
    body+='<h2>Đọc số đo</h2><ul><li>Rõ và HE đều gồm đọc model và tạo feature; HE còn gồm mã hóa, lưu phiên, HTTP worker và giải mã tại DN.</li><li>Loại một lượt làm nóng; mỗi lượt HE mới dùng yêu cầu mới, không lấy cache. Thời gian thường không gồm khởi động dịch vụ hoặc Portal/trình duyệt.</li><li>Top-5 trên mẫu 5 giao dịch không chứng minh lợi ích chọn cảnh báo. Các thứ tự được kiểm riêng.</li><li>Loopback, Mahalanobis hai feature; chưa suy rộng sang cloud công cộng hoặc bốn nhánh.</li></ul>'
    body+='<p><a href="REPORT.md">Báo cáo đầy đủ</a> · <a href="comparison.json">Dữ liệu đo từng lượt</a></p>'
    html='<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đối chiếu rõ và HE</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#17323b;max-width:1280px;margin:36px auto;padding:0 22px;background:#f7faf9}h1{font-size:30px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:12px;border:1px solid #d4dfdf;text-align:left}th{background:#e3efec}.scroll{overflow:auto}.note{background:#fff4d9;border-left:4px solid #af7800;padding:14px}a{color:#086c62}</style><body>'+body+'</body></html>'
    (output/'comparison.html').write_text(html,encoding='utf-8')
