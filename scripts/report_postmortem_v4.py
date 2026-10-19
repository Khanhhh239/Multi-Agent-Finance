"""Render the completed post-hoc synthetic v4 diagnostics without fitting models."""
from pathlib import Path
import json

ROOT = Path('results/v5/postmortem_v4/run3')
REPORT = Path('docs/03_danh_gia_va_hieu_qua_kinh_te/08_mo_xe_niem_phong_v4.md')
LABELS = {'S1_masked': 'S1 gốc', 'S2_original': 'S2 gốc', 'S1_drop_train': 'S1 loại khỏi huấn luyện',
          'S1_drop_train_valid': 'S1 loại khỏi huấn luyện và kiểm định', 'S1_unlabelled_0p2': 'S1 trọng số nhãn 0 bằng 0,2'}


def pct(value):
    return 'Không xác định' if value is None else f'{100*value:.2f}'.replace('.', ',')


def interval(point, limits):
    return f'{pct(point)} [{pct(limits[0])}; {pct(limits[1])}]'


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def main():
    summary, manifest = load('summary.json'), load('manifest.json')
    METHODS, PROTOCOLS = tuple(manifest['methods']), tuple(manifest['protocols'])
    assert summary['protected_artifacts_unchanged']
    worlds = ('s4_s931', 's4_s932', 's4_s933')
    protocols = {w: {p: load(f'{w}_{p}.json') for p in PROTOCOLS} for w in worlds}
    checks = [protocols[w][p]['original_baseline_check']['status'] for w in worlds for p in ('S1_masked', 'S2_original')]
    assert set(checks) == {'passed'}
    lines = ['# Mổ xẻ hậu kiểm v4 trên dữ liệu tổng hợp', '',
        'Ngày 2026-10-19. **Hậu kiểm, không phải niêm phong.** Chủ dự án đã cho phép dùng ba thế giới v4 đã lộ để chẩn đoán. Mọi số đo trong tài liệu là trên **dữ liệu tổng hợp**. Kết luận **v4 không đạt G5 và kích hoạt M2** giữ nguyên; không dùng bất kỳ biến thể nào dưới đây để viết lại kết quả v4 hoặc làm bằng chứng xác nhận v5.', '',
        '## Phạm vi và kiểm chứng', '',
        'Ba phương pháp: L3, L4-FB và `Novelty max(R,E)`; tên Novelty trong giao việc được hiểu là cấu hình khởi đầu lạnh đã chọn ở v4. Giữ nguyên sáu tệp khóa, các đặc trưng, hai cấu hình cây, seed, thời gian và ngân sách ba dòng mỗi công ty mỗi tuần. Dùng đúng bộ đệm đặc trưng v4 lịch sử, không dựng lại bằng bộ luật khác.', '',
        'Đã tái lập chỉ số S1 và S2 gốc cho cả ba phương pháp ở cả ba thế giới, đối chiếu các trường số ngoài AP, gồm cảnh báo, recall, vụ, ca khó và từng kịch bản với `results/v4/sealed_v4.json`, dung sai tuyệt đối 0,000000000001. Mọi phép đối chiếu qua trước khi thực hiện can thiệp của thế giới tương ứng. Tệp kết quả, khóa và báo cáo niêm phong v4 không đổi băm.', '',
        'Hai lượt đầu dừng vì AP L3 S1 931 lệch 0,00000000075098569 trong khi các chỉ số ngân sách khớp. Đã kiểm lại bằng đúng hàm thực thi gốc và vẫn thấy cùng sai khác. Từ lượt 3, chốt giữ nguyên dung sai cho toàn bộ trường ngoài AP, còn AP gốc, AP chạy lại và hiệu được lưu công khai dưới `original_baseline_check.ap_diagnostic_only` của từng JSON. AP không dùng trong R0 để chọn gì hoặc phân rã recall. Nguyên nhân chính xác của sai khác AP chưa xác định; không tuyên bố điểm thô trùng bit. Đây là sửa phạm vi kiểm tái lập, ghi trước mọi can thiệp, không phải thay mô hình hoặc cổng v4.', '',
        'Báo cáo niêm phong gốc không lưu cờ cảnh báo từng dòng. Vì vậy đối chiếu trên đây chứng minh các chỉ số tổng hợp và theo họ khớp, không chứng minh từng dòng được chọn giống hệt. Bootstrap R0 dùng cờ của lượt hậu kiểm; cờ P1 phát triển lấy từ NPZ gốc đã lưu.', '',
        'Mã: `agent2/postmortem_v4.py`. Kết quả hoàn chỉnh: `results/v5/postmortem_v4/run3/`; `manifest.json` ghi băm mã, CSV, bộ đệm, cờ P1 và tệp v4 được bảo vệ. JSON được lưu sau từng giao thức; tổng hợp tại `summary.json`. Hai manifest lần dừng trước được giữ ở thư mục cha và `run2`, không được dùng như kết quả hoàn chỉnh.', '',
        '## 1. Độ nhạy với nhãn chưa biết', '',
        'S1 gốc giữ dòng của bảy kịch bản mới trong lịch sử và đặt nhãn thành 0. Hai can thiệp loại bỏ dùng nhãn thật của dữ liệu tổng hợp để biết phải loại dòng nào: đây là đối chiếu biết trước, không phải cách xử lý khả thi khi vận hành. Biến thể trọng số giữ nguyên mọi dòng, nhân trọng số của **mọi dòng nhãn 0** trong huấn luyện với 0,2; không thử hệ số khác. Nhãn và AP kiểm định của biến thể này giữ nguyên. Cân bằng trọng số họ dương của L4-FB giữ nguyên.', '',
        'Tham chiếu của kênh Novelty và các đầu ra không nhãn đã tính sẵn giữ nguyên trong mọi biến thể; do đó Novelty là đối chứng không bị tác động trực tiếp bởi nhãn. Loại dòng huấn luyện cũng thay đổi số dòng và hệ số cân bằng lớp; hiệu ứng quan sát không được gọi là tác động nhân quả thuần của nhiễu nhãn.', '',
        'Trung bình đều ba thế giới, đơn vị phần trăm. Cột cuối là hiệu so với S1 gốc và khoảng bootstrap 95%, đơn vị điểm phần trăm.', '',
        '| Phương pháp | Giao thức | Recall chung | Đã biết | Mới | Báo nhầm ca khó | Hiệu recall so S1 gốc [95%] |',
        '|---|---|---:|---:|---:|---:|---:|']
    for method in METHODS:
        for mode in PROTOCOLS:
            fields = ('recall', 'known_recall', 'novel_recall', 'hard_neg_alert_rate')
            values = [sum(protocols[w][mode]['metrics'][method][f] for w in worlds) / 3 for f in fields]
            effect = summary['paired_label_effects'].get(mode, {}).get(method, {}).get('all')
            text = interval(effect['macro_estimate'], effect['macro_ci95']) if effect else 'Không áp dụng'
            lines.append(f'| {method} | {LABELS[mode]} | ' + ' | '.join(map(pct, values)) + f' | {text} |')
    lines += ['', 'Hiệu theo từng thế giới giúp tránh che mất bất ổn giữa các seed. Mọi khoảng dưới đây ghép cặp nguyên vụ trên cùng tập kiểm thử, không khớp lại mô hình.', '',
              '| Thế giới | Phương pháp | Loại huấn luyện [95%] | Loại cả kiểm định [95%] | Trọng số 0,2 [95%] |', '|---|---|---:|---:|---:|']
    for world in worlds:
        for method in METHODS:
            cells = []
            for mode in ('S1_drop_train', 'S1_drop_train_valid', 'S1_unlabelled_0p2'):
                item = summary['paired_label_effects'][mode][method]['all']['worlds'][world]
                cells.append(interval(item['estimate'], item['ci95']))
            lines.append(f'| {world} | {method} | ' + ' | '.join(cells) + ' |')
    lines += ['', 'JSON còn giữ riêng hiệu trên kịch bản đã biết và mới; không chọn biến thể tốt nhất làm cấu hình v5 từ bảng hậu kiểm này.', '',
              '## 2. Lịch lương và quy mô công ty', '',
              'Nhóm đổi lịch là các lịch ngày 1, ngày 20 hoặc ngày 7 và 22, đúng phép thay lịch trong bộ sinh v4 niêm phong; các lịch này không xuất hiện trong danh mục lịch phát triển. Nhóm quy mô lấy trực tiếp `size_class`, không phân nhóm lại theo kết quả. Chỉ tính dòng gian lận của các kịch bản **đã biết**. Các ô là recall phần trăm và khoảng bootstrap 95%.', '',
              '| Thế giới | Giao thức | Nhóm | Dòng gian lận | Vụ | L3 [95%] | L4-FB [95%] | Novelty [95%] |', '|---|---|---|---:|---:|---:|---:|---:|']
    for world in worlds:
        for mode in ('S1_masked', 'S2_original'):
            groups = summary['subgroups'][world][mode]['all_known']
            for key in ('pay_shift', 'size_class'):
                for tag, methods in groups[key].items():
                    first = methods[METHODS[0]]
                    cells = [interval(methods[m]['recall'], methods[m]['ci95']) for m in METHODS]
                    mark = ' †' if first['cases'] < 10 else ''
                    lines.append(f"| {world} | {LABELS[mode]} | {key}: {tag}{mark} | {first['rows']} | {first['cases']} | " + ' | '.join(cells) + ' |')
    lines += ['', '† Ít hơn 10 vụ; khoảng bootstrap có thể rất hẹp hoặc suy biến khi chỉ có một vụ. Đây không phải bằng chứng chắc chắn về nhóm doanh nghiệp thật. JSON giữ cả nhóm chéo lịch lương và quy mô để kiểm tra nhiễu do cơ cấu.', '',
              'Riêng các kịch bản lương đã biết:', '',
              '| Thế giới | Giao thức | Lịch | Dòng | Vụ | L3 [95%] | L4-FB [95%] | Novelty [95%] |', '|---|---|---|---:|---:|---:|---:|---:|']
    for world in worlds:
        for mode in ('S1_masked', 'S2_original'):
            for tag, methods in summary['subgroups'][world][mode]['known_payroll']['pay_shift'].items():
                first = methods[METHODS[0]]
                cells = [interval(methods[m]['recall'], methods[m]['ci95']) for m in METHODS]
                lines.append(f"| {world} | {LABELS[mode]} | {tag} | {first['rows']} | {first['cases']} | " + ' | '.join(cells) + ' |')
    lines += ['', 'Lịch lương không được can thiệp ngẫu nhiên độc lập với toàn bộ hồ sơ công ty trong hậu kiểm này. Khác biệt nhóm chỉ là liên hệ; không dùng nó để kết luận riêng lịch lương gây ra mức tụt.', '',
              '## 3. Tụt theo từng kịch bản đã biết', '',
              'Mỗi tỷ lệ là trung bình đều ba thế giới của giao thức tương ứng. Hiệu dương nghĩa là recall ở đích thấp hơn P1 phát triển; bảng được xếp theo hiệu giảm lớn nhất, riêng từng phương pháp và giao thức. Tất cả 30 kịch bản đều được giữ, kể cả hiệu âm. Số vụ trong bảng là tổng ba thế giới đích.']
    for method in METHODS:
        for mode in ('S1_masked', 'S2_original'):
            lines += ['', f'### {method}, P1 so với {LABELS[mode]}', '',
                      '| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |', '|---|---:|---:|---:|---:|---:|']
            for row in summary['family_drops'][method][mode]:
                lines.append(f"| `{row['family']}` | {pct(row['development_recall'])} | {pct(row['target_recall'])} | {pct(row['drop'])} | {row['target_cases']} | {row['target_fraud_rows']} |")
    lines += ['', '## 4. Vì sao seed 933 thấp nhất', '',
              'Bảng cấu trúc dưới đây giữ số vụ và cơ cấu che giấu; không coi ít dòng hoặc nhiều vụ L2 là nguyên nhân đủ để giải thích kết quả. Số dòng dương đã biết trong lịch sử là lượng nhãn dương S1 thật sự còn dùng được, trong khi S2 có nguồn học từ ba thế giới phát triển.', '',
              '| Thế giới | Dương đã biết train | Dương mới train | Dương đã biết validation | Vụ test | Dòng test | Dòng mới test | Vụ L0 test | Vụ L1 test | Vụ L2 test | Tỷ lệ L2 test (%) |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for world in worlds:
        comp = summary['composition'][world]
        c = comp['test']['concealment_cases']
        values = [comp['train']['known_rows'], comp['train']['novel_rows'], comp['validation']['known_rows'],
                  comp['test']['cases'], comp['test']['fraud_rows'], comp['test']['novel_rows'], c.get('L0', 0), c.get('L1', 0), c.get('L2', 0), pct(c.get('L2', 0) / comp['test']['cases'])]
        lines.append('| ' + world + ' | ' + ' | '.join(map(str, values)) + ' |')
    comp = summary['composition']['s4_s933']
    novel_share = comp['test']['novel_rows'] / comp['test']['fraud_rows']
    l2 = comp['test']['concealment_cases'].get('L2', 0)
    other_l2 = summary['composition']['s4_s932']['test']['concealment_cases'].get('L2', 0)
    lines += ['', f"933 chỉ có {comp['train']['known_rows']} dòng dương đã biết ở train, thấp nhất trong ba thế giới, trong khi có {comp['train']['novel_rows']} dòng mới bị đặt nhãn 0, cao nhất trong ba thế giới. Tập test có {comp['test']['cases']} vụ và {pct(novel_share)}% dòng gian lận thuộc kịch bản mới. Tuy vậy, 933 có {l2} vụ L2 ở test, ít hơn {other_l2} vụ của 932; không có bằng chứng rằng chỉ nhiều vụ che giấu khó hơn đã đủ giải thích thứ hạng. Số dòng, số vụ, tỷ trọng họ và chất lượng nguồn nhãn đều cùng thay đổi, nên phải đọc cùng các can thiệp và phân rã dưới đây."]
    lines += ['', 'Đối chiếu 933 với trung bình đều 931 và 932 của cả ba phương pháp. Phân rã theo họ giữ đúng tổng: phần cơ cấu dùng tỷ trọng dòng theo họ; phần trong họ là khác biệt tỷ lệ phát hiện khi giữ tỷ trọng 933. Hai phần chỉ là mô tả, không chứng minh nguyên nhân. Các bảng đóng góp từng họ bên dưới tập trung cấu hình đã chọn L4-FB; JSON giữ đủ ba phương pháp.', '',
              '| Phương pháp | Giao thức | Recall 931 và 932 | Recall 933 | Chênh tổng (điểm) | Phần cơ cấu | Phần trong họ |', '|---|---|---:|---:|---:|---:|---:|']
    for mode in ('S1_masked', 'S2_original'):
        for method in METHODS:
            gap = summary['world_933_gap'][mode][method]
            lines.append(f"| {method} | {LABELS[mode]} | {pct(gap['reference_recall'])} | {pct(gap['subject_recall'])} | {pct(gap['gap'])} | {pct(gap['composition_component'])} | {pct(gap['within_family_component'])} |")
    for mode in ('S1_masked', 'S2_original'):
        gap = summary['world_933_gap'][mode]['L4-FB']
        lines += ['', f'Các họ đóng góp chênh lệch lớn nhất ở {LABELS[mode]}:', '',
                  '| Họ | Phần cơ cấu (điểm) | Phần trong họ (điểm) | Tổng (điểm) |', '|---|---:|---:|---:|']
        for row in gap['by_family'][:12]:
            lines.append(f"| `{row['family']}` | {pct(row['composition'])} | {pct(row['within_family'])} | {pct(row['total'])} |")
    lines += ['', 'Cơ cấu toàn bộ kịch bản, số dòng và số vụ theo train, validation, test của từng thế giới có đầy đủ trong `summary.json`. Bảng hiệu can thiệp ở mục 1 cho biết mức hồi phục của 933 khi xử lý nhãn; phần còn lại không thể tự quy hết cho nhãn, lịch lương hoặc che giấu. Chỉ ba thế giới và vài vụ mỗi họ không đủ nhận diện một nguyên nhân duy nhất.', '',
              '## 5. Phân rã mức tụt 39,5 điểm và bootstrap theo vụ', '',
              'Chuỗi đối chiếu A đến F: A là recall P1 phát triển từ cờ gốc; B dùng tỷ lệ P1 theo họ nhưng tái trọng số theo cơ cấu họ đã biết ở đích; C là recall S2 trên kịch bản đã biết; D là recall S2 chung; E là recall S1 chỉ loại dòng mới khỏi huấn luyện; F là recall S1 gốc. Lấy hiệu liên tiếp A trừ B đến E trừ F nên tổng cộng đúng A trừ F. Dấu âm nghĩa là phần đó bù lại mức giảm theo thứ tự này.', '',
              'Đây là **đồng nhất thức mô tả phụ thuộc thứ tự**, không phải phân bổ nhân quả duy nhất. Phần D trừ E còn gộp nguồn, số lượng và cơ cấu huấn luyện, cùng khác biệt lịch sử kiểm định. Phần E trừ F là can thiệp loại dòng biết trước, bao gồm thay đổi số dòng và cân bằng lớp. Không đặt tên các phần này là tác động thuần của dịch chuyển hoặc nhiễu nhãn.', '']
    component_names = {'known_family_composition': 'A trừ B: cơ cấu họ đã biết', 'known_conditional_transfer': 'B trừ C: chuyển giao có điều kiện trong họ đã biết',
                       'novel_mixture_under_S2': 'C trừ D: đưa kịch bản mới vào hỗn hợp S2', 'training_source_and_history_residual': 'D trừ E: nguồn huấn luyện và lịch sử còn gộp',
                       'remove_novel_training_rows_intervention': 'E trừ F: can thiệp loại dòng mới khỏi huấn luyện'}
    for method in METHODS:
        item = summary['decomposition'][method]
        lines += [f'### {method}', '', '| Thành phần | Điểm phần trăm [95%] |', '|---|---:|']
        for name, estimate in item['components'].items():
            lines.append(f"| {component_names[name]} | {interval(estimate['estimate'], estimate['ci95'])} |")
        total = item['total']
        lines += [f"| Tổng A trừ F | **{interval(total['estimate'], total['ci95'])}** |", '',
                  'Mức recall tại từng điểm A đến F: ' + '; '.join(f'{key} = {pct(value)}%' for key, value in item['levels'].items()) + '.', '',
                  f"Sai số cộng số học: {item['identity_residual']:.12f} theo thang recall.", '']
    lines += ['Bootstrap 2.000 lần, seed 20261019, lấy nguyên vụ. Phát triển tái lấy mẫu trong từng thế giới và họ để các tỷ lệ theo họ luôn xác định; đích tái lấy mẫu trong từng thế giới, cùng mẫu vụ cho các giao thức. Không khớp lại mô hình hoặc chọn lại ngân sách trong bootstrap. Các khoảng có điều kiện trên ba thế giới, số vụ theo họ phát triển và mô hình cố định; không bao gồm phương sai huấn luyện, lựa chọn phương pháp hoặc sinh thế giới mới. Khoảng mô tả không được hiểu là mức đảm bảo trên doanh nghiệp thật.', '',
              'P1 trong tệp khóa v4 đã làm tròn bốn chữ số thập phân; phép phân rã dùng cờ P1 gốc để cộng chính xác, nên có thể khác vài phần rất nhỏ của một điểm so với phép trừ trên số đã làm tròn. Các giới hạn từng thành phần không cộng được bằng cách cộng hai đầu khoảng; khoảng của tổng được tính trực tiếp trên cùng mẫu bootstrap.', '',
              '## Kết luận và giới hạn vòng mới', '',
              'V4 **không đạt G5**, giữ nguyên kết luận M2. Các kiểm nhãn trong R0 không phải giải pháp vận hành đã được kiểm chứng; không chọn ứng viên theo bảng hậu kiểm hoặc dùng ba seed v4 để xác nhận v5. Cần đăng ký giao thức v5 trước R2, chọn theo thế giới phát triển tệ nhất và đánh giá một lần trên kịch bản v5 chưa từng được nhóm phương pháp đọc khi phát triển.', '',
              'Bản đăng ký trước tại `docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md` là đề xuất để chủ dự án duyệt. **Dừng sau R0 và R1; không bắt đầu R2 khi chưa nhận “duyệt”.** Chưa tải dữ liệu ngoài, chưa sinh hoặc chạy niêm phong v5, chưa có dữ liệu doanh nghiệp thật.', '']
    ap_table = ['AP so sánh toàn bộ thứ hạng, không phải recall tại ngân sách. Bảng dưới dùng thang AP từ 0 đến 1, ghi đủ chữ số để đối chiếu sai khác; không thay số lịch sử.', '',
                '| Thế giới | Giao thức | Phương pháp | AP lịch sử | AP hậu kiểm | Hiệu |', '|---|---|---|---:|---:|---:|']
    for world in worlds:
        for mode in ('S1_masked', 'S2_original'):
            for method, values in protocols[world][mode]['original_baseline_check']['ap_diagnostic_only'].items():
                cells = [f"{values[k]:.12f}".replace('.', ',') for k in ('historical', 'rerun')]
                delta = f"{values['delta']:.3e}".replace('.', ',')
                ap_table.append(f"| {world} | {LABELS[mode]} | {method} | {cells[0]} | {cells[1]} | {delta} |")
    ap_table.append('')
    max_ap_delta = max(abs(values['delta']) for w in worlds for p in ('S1_masked', 'S2_original')
                       for values in protocols[w][p]['original_baseline_check']['ap_diagnostic_only'].values())
    ap_table += [f"Ở lượt hoàn chỉnh, chênh AP tuyệt đối lớn nhất của 18 cặp là {max_ap_delta:.12g}. Hai sai khác của lượt đã dừng vẫn được giữ trong lịch sử; không vì lượt cuối khớp mà xóa dấu vết đó.", '']
    index = lines.index('## 1. Độ nhạy với nhãn chưa biết')
    lines[index:index] = ap_table
    drop = summary['paired_label_effects']['S1_drop_train']['L4-FB']['all']
    weight = summary['paired_label_effects']['S1_unlabelled_0p2']['L4-FB']['all']
    gap = summary['world_933_gap']['S1_masked']['L4-FB']
    total = summary['decomposition']['L4-FB']['total']
    highlights = ['## Các kết quả chính của hậu kiểm', '',
        f"- Can thiệp biết trước loại dòng mới chỉ khỏi huấn luyện làm recall L4-FB thay đổi **{interval(drop['macro_estimate'], drop['macro_ci95'])} điểm phần trăm**, trung bình đều ba thế giới. Đây là can thiệp dùng nhãn thật tổng hợp, không phải kết quả triển khai.",
        f"- Giảm trọng số mọi nhãn 0 xuống 0,2 làm recall L4-FB thay đổi **{interval(weight['macro_estimate'], weight['macro_ci95'])} điểm phần trăm**. Không chọn một hệ số khác sau kết quả này.",
        f"- Chênh S1 L4-FB giữa trung bình 931, 932 và seed 933 là {pct(gap['gap'])} điểm; phần cơ cấu họ là {pct(gap['composition_component'])}, phần tỷ lệ phát hiện trong họ là {pct(gap['within_family_component'])}. Đây là phân rã mô tả, không phải chứng minh nhân quả.",
        f"- Tổng tụt P1 trừ S1 của L4-FB là **{interval(total['estimate'], total['ci95'])} điểm**; năm thành phần tại mục 5 cộng đúng về tổng này. V4 vẫn không đạt G5.", '']
    index = lines.index('## Phạm vi và kiểm chứng')
    lines[index:index] = highlights
    lines += ['## Tái lập hậu kiểm', '',
              'Yêu cầu dữ liệu, bộ đệm và cờ P1 lịch sử còn tồn tại, đúng băm. Dùng một thư mục ra mới để giữ nguyên báo cáo đã bàn giao. Lệnh dưới chỉ chạy lại hậu kiểm v4 đã lộ, không phải một lượt niêm phong mới và không phải R2.', '',
              '```powershell', '$env:PYTHONPATH = (Get-Location).Path', "$env:PYTHONIOENCODING = 'utf-8'",
              '.venv/Scripts/python.exe -m agent2.postmortem_v4 --out work/reproduce_postmortem_v4', '```', '',
              'Khoảng bootstrap can thiệp riêng và khoảng trong chuỗi phân rã dùng cách tổ chức mẫu khác nhau với cùng 2.000 lần lặp; biên có thể khác nhẹ do Monte Carlo. Trong mỗi chuỗi phân rã, mọi thành phần và tổng dùng chung mẫu.', '']
    REPORT.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(str(REPORT))


if __name__ == '__main__':
    main()
