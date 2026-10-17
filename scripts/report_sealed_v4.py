"""Archive the single sealed run and assess the documented G5 and stop rules."""
from pathlib import Path
import json
import shutil
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from agent2.world_v4_sealed import NOVEL


def main():
    source = Path("work/results/sealed_v4.json")
    result = json.loads(source.read_text(encoding="utf-8"))
    assert set(result["worlds"]) == {"s4_s931", "s4_s932", "s4_s933"}
    frozen, worlds = result["frozen"], result["worlds"]
    chosen = frozen["chosen"]
    p1 = frozen["dev_scores"][chosen]["P1"]
    gates, stop_reasons = {}, []
    fields = ("recall", "known_recall", "novel_recall", "case_recall", "new_decoy_alert_rate", "hard_neg_alert_rate")
    lines = ["# Kết quả niêm phong v4 trên dữ liệu tổng hợp", "",
             f"Ngày {dt.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()}. Đây là báo cáo hoàn chỉnh đầu tiên của ba seed 931 đến 933, sau khi đóng băng và thử khô seed 939 thành công. Lần thực thi trước dừng do lỗi cấp phát bộ nhớ, chưa ghi tệp kết quả hoặc in chỉ số từng phần; chạy lại theo ngoại lệ hạ tầng của A5. Không điều chỉnh phương pháp hoặc chọn lại cấu hình theo kết quả này.", "",
             f"Cấu hình đã chọn: **{chosen}**. Khởi đầu lạnh: **{frozen['cold_start']}**. Ngân sách ba dòng mỗi công ty mỗi tuần. S1 ẩn nhãn bảy kịch bản mới trong lịch sử của công ty; S2 học có giám sát từ ba thế giới phát triển và dùng lịch sử không nhãn của công ty đích.", "",
             "## Cấu hình đã chọn", "",
             "Đơn vị phần trăm. Số vụ được thể hiện bằng tỷ lệ vụ tìm thấy; số dòng gian lận kiểm thử và dòng mới có trong JSON gốc.", "",
             "| Thế giới | Giao thức | Recall chung | Đã biết | Mới | Vụ tìm thấy | Báo nhầm ca mới | Báo nhầm toàn bộ ca khó | Giảm so P1 (điểm) | G5 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|"]
    for name, world in worlds.items():
        gates[name] = {}
        for scenario in ("S1", "S2"):
            r = world[scenario][chosen]
            if not all(np.isfinite(r[k]) for k in fields):
                raise ValueError(f'undefined sealed metrics: {name} {scenario}; do not proceed to training')
            conditions = {"recall_at_least_65": r["recall"] >= .65,
                          "novel_recall_at_least_30": r["novel_recall"] >= .30,
                          "new_decoy_at_most_20": r["new_decoy_alert_rate"] <= .20,
                          "absolute_gap_to_dev_p1_at_most_15pp": abs(p1 - r["recall"]) <= .15}
            gates[name][scenario] = {"passed": all(conditions.values()), "conditions": conditions,
                                     "dev_p1": p1, "metrics": {k: r[k] for k in fields}}
            metrics = " | ".join(f"{100*r[k]:.2f}" for k in fields)
            lines.append(f"| {name} | {scenario} | {metrics} | {100*(p1-r['recall']):.2f} | {'Đạt' if all(conditions.values()) else 'Không đạt'} |")
    means = {}
    for scenario in ("S1", "S2"):
        means[scenario] = {k: float(np.mean([w[scenario][chosen][k] for w in worlds.values()])) for k in fields}
        if means[scenario]['recall'] < .50 or means[scenario]['hard_neg_alert_rate'] > .25:
            stop_reasons.append({'aggregation': 'equal mean over three worlds', 'scenario': scenario,
                                 'recall': means[scenario]['recall'], 'hard_neg_alert_rate': means[scenario]['hard_neg_alert_rate']})
        metrics = " | ".join(f"{100*means[scenario][k]:.2f}" for k in fields)
        lines.append(f"| Trung bình đều | {scenario} | {metrics} | {100*(p1-means[scenario]['recall']):.2f} | Xem từng thế giới |")
    passed_all_worlds = all(item["passed"] for world in gates.values() for item in world.values())
    macro_gates = {scenario: {'recall_at_least_65': r['recall'] >= .65,
                              'novel_recall_at_least_30': r['novel_recall'] >= .30,
                              'new_decoy_at_most_20': r['new_decoy_alert_rate'] <= .20,
                              'absolute_gap_to_dev_p1_at_most_15pp': abs(p1 - r['recall']) <= .15}
                   for scenario, r in means.items()}
    passed = all(all(conditions.values()) for conditions in macro_gates.values())
    lines += ["", "## Kết luận cổng", "",
              f"G5 {'đạt' if passed else 'không đạt'} theo trung bình đều ba thế giới, kiểm riêng S1 và S2, cùng cách tổng hợp các thế giới ở G1. Bảng phía trên giữ cả kết quả từng thế giới; toàn bộ sáu cặp riêng lẻ {'đều đạt' if passed_all_worlds else 'không đồng loạt đạt'}. Bảng kiểm máy đọc được ở `results/v4/sealed_gates.json`. P1 phát triển của cấu hình chọn là {100*p1:.2f}%; chênh so với niêm phong là khác biệt phân phối tổng hợp, không đo mức suy giảm trên doanh nghiệp thật.", "",
              "**Điều kiện dừng toàn dự án đã kích hoạt.** Dừng phát triển và triển khai tiếp; báo chủ dự án xem lại bài toán theo mục điều kiện dừng của kế hoạch." if stop_reasons else "Trung bình ba thế giới của mỗi giao thức không có recall chung dưới 50% hoặc báo nhầm toàn bộ ca khó trên 25%; chưa kích hoạt điều kiện dừng toàn dự án của M2.", ""]
    if not passed:
        lines += ["Theo quy tắc G5, quay lại phát triển và cần tập niêm phong mới cho vòng sau. Không chỉnh mô hình trên ba seed này rồi chạy lại. Mô hình hoặc công cụ cục bộ sau A5 chỉ là hiện vật nghiên cứu, chưa được chấp nhận để thí điểm.", ""]
    lines += ["## Bảy kịch bản mới, tất cả ứng viên", "",
              "Các ô là recall phần trăm, trung bình đều theo ba thế giới. JSON gốc giữ số từng thế giới. Bảng chỉ phục vụ chẩn đoán; cấu hình đã chọn không thay đổi.", ""]
    for scenario in ("S1", "S2"):
        families = sorted(NOVEL)
        lines += [f"### {scenario}", "", "| Cấu hình | " + " | ".join(families) + " |",
                  "|---|" + "---:|" * len(families)]
        first = next(iter(worlds.values()))
        for method in first[scenario]:
            values = [np.mean([w[scenario][method]["by_family"].get(f, np.nan) for w in worlds.values()]) for f in families]
            lines.append("| " + method + " | " + " | ".join(f"{100*v:.1f}" for v in values) + " |")
        lines.append("")
    lines += ["## Hạn chế", "",
              "Bộ sinh, kịch bản và phương pháp do cùng nhóm phát triển, nên niêm phong v4 chưa độc lập tuyệt đối. `overtime_inflation_group` gần `payroll_padding`; chưa thêm CUSUM hoặc đặc trưng nhắm vào kịch bản mới trước niêm phong. Kết quả có thể thuận lợi hơn thực tế vì cùng người thiết kế đặc trưng và dữ liệu.", "",
              "Mọi số liệu là tổng hợp. Nhãn ẩn mô phỏng gian lận chưa được phát hiện, không thay thế điều tra nghiệp vụ. Chưa có dữ liệu doanh nghiệp, xác nhận độc lập, đánh giá người dùng hoặc hiệu quả kinh tế thật.", ""]
    output = {"data_kind": "synthetic", "chosen": chosen, "g5_passed_all_world_scenarios": passed_all_worlds,
              'g5_passed_macro_scenarios': passed, 'macro_gate_conditions': macro_gates,
              "global_stop_triggered": bool(stop_reasons), "global_stop_reasons": stop_reasons,
              "worlds": gates, "macro_world_means": means, "selection_changed": False, "sealed_reuse_permitted": False}
    Path("results/v4/sealed_gates.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(source, "results/v4/sealed_v4.json")
    Path("docs/03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"chosen": chosen, "G5": passed, "global_stop": bool(stop_reasons), "means": means}, indent=2))


if __name__ == "__main__":
    main()
