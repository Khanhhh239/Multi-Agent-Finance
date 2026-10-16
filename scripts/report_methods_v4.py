"""Archive the completed development study and render its paired comparisons."""
from pathlib import Path
import json
import shutil

from agent2.select_v4 import table


def main():
    source = Path("work/results/v4_methods")
    destination = Path("results/v4/method_study")
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(source.glob("w4_s*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        assert len(result["P1"]) == len(result["P3"]) == 24
        assert len(result["P2"]) == 10
        results.append(result)
        shutil.copy2(path, destination / path.name)
    assert len(results) == 3
    summary = table(results)
    summary.to_csv(destination / "development_table.csv", index=False)
    boot = json.loads(Path("results/v4/paired_bootstrap.json").read_text(encoding="utf-8"))
    lines = ["# So sánh phương pháp v4 trên dữ liệu tổng hợp", "",
             "Ngày 2026-10-16. Ba thế giới phát triển 411, 412, 413; 24 cấu hình; P2 trung bình đều theo 10 nhánh ACFE. Không dùng tập niêm phong để chọn cấu hình.", "",
             "## Điểm phát triển", "",
             "Các số trong bảng là phần trăm. P1 là cùng thế giới theo thời gian; P2 bỏ một nhánh; P3 chuyển sang thế giới mới.", "",
             "| Cấu hình | P1 | P2 | P3 | Điểm | Báo nhầm ca khó P1 | Đủ điều kiện |",
             "|---|---:|---:|---:|---:|---:|:---:|"]
    for r in summary.to_dict("records"):
        lines.append(f"| {r['config']} | {100*r['P1']:.2f} | {100*r['P2']:.2f} | {100*r['P3']:.2f} | {100*r['score']:.2f} | {100*r['P1_decoy']:.2f} | {'Có' if r['eligible'] else 'Không'} |")
    lines += ["", "## Chênh lệch ghép cặp so với L3 ở P1", "",
              "Bootstrap 2.000 lần, seed 0, lấy lại mẫu toàn bộ vụ theo khóa công ty và vụ, dùng cùng lần lấy cho hai cấu hình. Giữ cố định cờ cảnh báo và ngân sách đã chọn; không chọn lại ngưỡng trong từng lần lấy mẫu. Dòng hợp lệ không ảnh hưởng hai chỉ số recall nên được tích phân bỏ qua chính xác. Khoảng là percentile 95%, không hiệu chỉnh nhiều so sánh.", "",
              "| Thế giới | Cấu hình trừ L3 | Hiệu recall (điểm phần trăm) | Khoảng 95% | Hiệu số vụ tìm thấy | Khoảng 95% |",
              "|---|---|---:|---|---:|---|"]
    for world, comparisons in boot.items():
        for name, stats in comparisons.items():
            recall, cases = stats['recall_delta'], stats['found_cases_delta']
            lines.append(f"| {world.removesuffix('_P1_alerts')} | {name} | {100*recall['estimate']:.2f} | [{100*recall['ci95'][0]:.2f}; {100*recall['ci95'][1]:.2f}] | {cases['estimate']:.0f} | [{cases['ci95'][0]:.0f}; {cases['ci95'][1]:.0f}] |")
    lines += ["", "## Kết luận theo giả thuyết đã đặt", "",
              "H1 chưa đạt: L4 và L4-FB tăng P2 trung bình so với L3 nhưng P3 không hơn L3 5 điểm phần trăm; các khoảng P1 không loại trừ 0. Không thể kết luận phương pháp lai vượt L3 chắc chắn.", "",
              "Cân bằng họ tăng P2 của L3 từ 51,95% lên 57,22%, trong khi P1 giảm 0,18 điểm; đây là tín hiệu phát triển cho H2, chưa đạt đầy đủ tiêu chí H1 về P3 và khoảng tin cậy. Hai tầng C-L4 không cải thiện đồng đều P1, P2, P3 so với L4. Biến thể trí nhớ không nhãn của H3 chưa được thử ở pha này.", "",
              "Bộ chọn giữ nguyên ràng buộc báo nhầm P1 không quá 20%; nếu chênh điểm nhỏ hơn 0,01 thì chọn ứng viên đứng trước. Vì thế cấu hình được chọn có thể khác ứng viên có điểm số lớn nhất. Kết quả chính thức nằm trong `results/v4/v4_frozen.json` sau A3.", "",
              "Thực thi ba ứng viên độc lập bằng ba luồng giữ nguyên thứ tự và tham số. Hồi quy P1 411 cho cờ cảnh báo của toàn bộ 24 cấu hình giống hệt bản nối tiếp trên 50.713 dòng; bằng chứng `results/v4/execution_regression.json`. Mọi số liệu chỉ mô tả dữ liệu tổng hợp, không phải độ chính xác thực tế.", ""]
    output = Path("docs/03_danh_gia_va_hieu_qua_kinh_te/06_so_sanh_phuong_phap_v4.md")
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == '__main__':
    main()
