"""Prepare a two-model handoff from fixed benchmark results; no prediction/fitting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

import numpy as np
import pandas as pd

from analysis.benchmark_t1_khanh_vs_v6 import ROOT, sha, write_json
from analysis.benchmark_t1_v6_final_vs_khanh import DEFAULT, BASE, PRACTICAL
from analysis.finalize_t1_v6_comparison import number, pct, ci


def main():
    out = ROOT / "outputs/analysis/t1_v6_vs_khanh_only_20261105"
    out.mkdir(parents=True, exist_ok=False)
    report = ROOT / "docs/03_Evaluation/T1_V6_PROGRESS_VS_KHANH_2026-11-05.md"
    history = report.with_name("T1_V6_PROGRESS_VS_KHANH_RESEARCH_FREEZE_DETAIL_2026-11-05.md")
    if history.exists():
        raise ValueError("Historical report already exists")
    shutil.copy2(report, history)
    review = json.loads((DEFAULT / "report_review.json").read_text(encoding="utf-8"))
    if sha(history) != review["report_sha256"]:
        raise ValueError("Previous report differs from its recorded version")
    source_hashes = {}
    for name in ("summary.json", "scores.csv", "aggregate_scores.csv", "primary_by_world.csv",
                 "bootstrap.csv", "quantiles_restricted120.csv", "slices_equal_world.csv",
                 "protocol.lock.json", "verification.json", "report_review.json"):
        source_hashes[(DEFAULT / name).relative_to(ROOT).as_posix()] = sha(DEFAULT / name)
    summary = json.loads((DEFAULT / "summary.json").read_text(encoding="utf-8"))
    protocol = json.loads((DEFAULT / "protocol.lock.json").read_text(encoding="utf-8"))
    for path, digest in protocol["protected"].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"Protected input changed: {path}")
    selected = ["khanh_refit", "v6_final"]
    scores = pd.read_csv(DEFAULT / "scores.csv", float_precision="round_trip")
    scores = scores[scores.model.isin(selected)].dropna(axis=1, how="any")
    aggregate = pd.read_csv(DEFAULT / "aggregate_scores.csv", float_precision="round_trip")
    aggregate = aggregate[aggregate.model.isin(selected)].dropna(axis=1, how="any")
    primary = pd.read_csv(DEFAULT / "primary_by_world.csv", float_precision="round_trip")
    primary = primary[["world", "role", "n", "khanh_primary", "final_primary", "improvement_pct", "firms",
                       "delta_v6_minus_khanh", "ci_low", "ci_high", "replicates"]]
    bootstrap = pd.read_csv(DEFAULT / "bootstrap.csv", float_precision="round_trip")
    quantiles = pd.read_csv(DEFAULT / "quantiles_restricted120.csv", float_precision="round_trip")
    quantiles = quantiles[quantiles.model.isin(selected)]
    slices = pd.read_csv(DEFAULT / "slices_equal_world.csv", dtype={"group": str}, float_precision="round_trip")
    for label, data in (("scores.csv", scores), ("aggregate_scores.csv", aggregate),
                        ("primary_by_world.csv", primary), ("bootstrap.csv", bootstrap),
                        ("quantiles_restricted120.csv", quantiles), ("slices_equal_world.csv", slices)):
        data.to_csv(out / label, index=False)
    p = summary["primary"]
    if not np.isclose(primary.khanh_primary.mean(), p["khanh"], atol=1e-15) or not np.isclose(primary.final_primary.mean(), p["v6_final"], atol=1e-15):
        raise ValueError("Filtered results changed the primary scores")
    def metric(model, day):
        return aggregate[(aggregate.model == model) & (aggregate.day == day)].iloc[0]
    old365, new365 = metric("khanh_refit", 365), metric("v6_final", 365)
    reduction365 = 100 * (1 - new365.paid_brier / old365.paid_brier)
    old_q = quantiles[quantiles.model == "khanh_refit"].select_dtypes(include="number").mean()
    new_q = quantiles[quantiles.model == "v6_final"].select_dtypes(include="number").mean()
    q_reduction = 100 * (1 - new_q.restricted_pinball120 / old_q.restricted_pinball120)
    mae_reduction = old_q.restricted_median_mae120 - new_q.restricted_median_mae120
    write_json(out / "comparison_summary.json", {
        "models": selected, "anchors": 65221, "worlds": 6,
        "primary": {k: p[k] for k in ("khanh", "v6_final", "improvement_vs_khanh_pct", "delta_vs_khanh", "ci_low", "ci_high")},
        "brier365_improvement_pct": reduction365,
        "worlds_v6_better_primary": summary["worlds_final_better_than_khanh"],
        "restricted_pinball120_improvement_pct": q_reduction,
        "restricted_median_mae_reduction_days": mae_reduction,
    })
    write_json(out / "comparison_protocol.json", {
        "scope": "T1 Khanh native default refit versus fixed Nov-05 V6; Paid and restricted quantiles only",
        "baseline_commit": "70c0ceb0653161f70535b4c8b9fb3cee63b7405f",
        "baseline_warning": "default native refit, not recovered pushed booster or all tuned/BLEND/CQR variants",
        "candidate_sha256": summary["candidate_sha256"], "fit_snapshots_each": 200000,
        "primary": protocol["primary"], "days": protocol["days"],
        "aggregation": "equal weight per World", "bootstrap": protocol["bootstrap"],
        "evaluation_scope": "retrospective synthetic; all six Worlds previously inspected",
        "fit_or_selection_during_packaging": False, "original_evaluation_protocol_sha256": sha(DEFAULT / "protocol.lock.json"),
        "source_results_sha256": source_hashes,
    })
    rel = "../../outputs/analysis/t1_v6_vs_khanh_only_20261105/"
    lines = [
        "# So sánh T1 của Khánh và T1 v6 ngày 05/11", "",
        "**Ngày 05/11/2026. Phạm vi: so sánh hai mô hình trên cùng 65.221 anchor thuộc sáu World synthetic, tập trung vào xác suất trả đủ và phân vị thời điểm trả đủ.**", "",
        f"**Kết luận: T1 v6 ngày 05/11 tốt hơn đối chứng T1 Khánh về xác suất trả đủ trong benchmark này.** Brier Paid chính 28/91 ngày giảm **{number(p['improvement_vs_khanh_pct'],2)}%**, thấp hơn ở **{summary['worlds_final_better_than_khanh']}/6 World**; Brier Paid 365 ngày giảm **{number(reduction365,2)}%**. Cải thiện thời điểm trả đủ nhỏ hơn: pinball giới hạn 120 ngày giảm **{number(q_reduction,2)}%**, MAE median giảm khoảng **{number(mae_reduction,2)} ngày**.", "",
        "Đối chứng Khánh là **HazardGBM mặc định từ commit `70c0ceb` ngày 24/10/2026, tái train trên cùng tập fit**. Chưa xác nhận được booster lịch sử đã push; kết luận chưa bao quát mọi cấu hình tuned, BLEND/CQR mà Khánh có thể đang sử dụng. V6 được chấm là nhánh **ngành + hành vi ledger (`both`), 93 feature snapshot**, đã chọn trên nguồn và giữ nguyên weights trước lần đối chiếu.", "",
        "**Kết quả theo nhiệm vụ.**", "",
        "| Nhiệm vụ chung | Kết quả | Đánh giá |", "|---|---|---|",
        f"| Xác suất trả đủ 28/91 ngày | Brier {number(p['khanh'])} → {number(p['v6_final'])}; giảm {number(p['improvement_vs_khanh_pct'],2)}% | V6 cải thiện trung bình, mức tăng nhỏ |",
        f"| Xác suất trả đủ 365 ngày | Brier {number(old365.paid_brier)} → {number(new365.paid_brier)}; giảm {number(reduction365,2)}% | V6 cải thiện rõ trong benchmark |",
        f"| Phân vị trả đủ, mục tiêu giới hạn 120 ngày | Pinball giảm {number(q_reduction,2)}%; MAE median giảm {number(mae_reduction,2)} ngày | Cải thiện nhỏ về thời điểm |", "",
        "**Thiết kế hai mô hình.**", "",
        "| Thành phần | T1 Khánh tái train | T1 v6 ngày 05/11 |", "|---|---|---|",
        "| Estimator | HazardGBM nhị phân Paid | Competing risks Open/Paid/Write-off |",
        "| Chân trời học | 13 tuần | 53 tuần |",
        "| Sau tuần 13 | Đuôi hình học; hazard kẹp [0,02; 0,6] | Tiếp tục dùng hazard được học |",
        "| Feature snapshot + tuần | 46 + 7 | 93 + 7 |",
        "| Vòng / leaves | 600 / 63 | 160 / 31 |",
        "| Learning rate / L2 | 0,05 / 5 | 0,05 / 8 |",
        "| Feature fraction / bagging fraction | 0,80 / 0,80 | 0,85 / 0,85 |",
        "| Seed | 7 | 20261101 |",
        "| Hàng risk set fit | 1.561.446 | 2.589.709 |",
        "| Risk set | Write-off tiếp tục là không Paid trong nhãn T1 cũ | Dừng ở mọi cause đóng |",
        "| Calibration | Mặc định, không thêm BLEND/CQR | Identity |", "",
        "V6 có thêm 47 feature snapshot: 18 biến lịch sử rủi ro/cơ cấu quá hạn/thu từng phần, 14 one-hot ngành mua/bán và 15 biến động ledger as-of. Lịch sử khách, trend và lịch thanh toán đã có trong T1 Khánh, nên không tính lại chúng thành đóng góp mới. Thêm feature không tự chứng minh từng feature đều cần thiết; đây là đối chứng toàn bộ phiên bản.", "",
        "**Cách giữ đối chứng chung.** Hai bên dùng đúng 200.000 snapshot fit, từ 128 công ty nguồn, gồm 100.028 hóa đơn riêng biệt. Thứ tự và 46 feature chung giống nhau theo builder hiện tại; công ty calibration không được trộn vào fit. Chân trời, risk set và cấu hình riêng của từng phiên bản được giữ nguyên; không chuẩn hóa về cùng số vòng/ngân sách tính toán.", "",
        "Tập đánh giá gồm 25.162 anchor validation, 20.336 test và 19.723 holdout tạo ngày 01/11; mỗi World 40 công ty. Mỗi hóa đơn có một anchor đầu tiên đủ điều kiện, cutoff 01/07–16/12/2024, đủ follow-up 365 ngày. Hai mô hình được chấm trên đúng cùng khóa/thứ tự, nhãn và dư nợ. Dự báo Khánh được dùng lại nguyên vẹn; lần chấm V6 không fit, hiệu chỉnh hoặc tìm tham số.", "",
        "Chỉ số chính đã khóa là trung bình Brier Paid ở 28 và 91 ngày trong từng World, rồi trung bình sáu World bằng trọng số. ECE cũng tính riêng từng World trước khi lấy trung bình. Brier/ECE nhỏ hơn là tốt hơn; giảm % là giảm sai số tương đối. Paid nghĩa là trả đủ, không phải chỉ có một khoản thu từng phần.", "",
        "**Xác suất Paid theo sáu chân trời.**", "",
        "| Ngày từ cutoff | Brier Khánh | Brier V6 | V6 giảm Brier | ECE Khánh → V6 |", "|---|---:|---:|---:|---:|",
    ]
    for day in protocol["days"]:
        a, b = metric("khanh_refit",day), metric("v6_final",day)
        lines.append(f"| {day} | {number(a.paid_brier)} | {number(b.paid_brier)} | {number(100*(1-b.paid_brier/a.paid_brier),2)}% | {number(a.paid_ece,5)} → {number(b.paid_ece,5)} |")
    lines += ["", "V6 giảm Brier ở cả sáu chân trời trung bình. ECE 28 ngày lại tăng nhẹ **0,04207 → 0,04267**, nên V6 chưa thắng đồng đều về calibration. Sau 91 ngày Khánh dùng đuôi ngoại suy, V6 tiếp tục dùng hazard được học; lợi thế dài hạn cần được hiểu trong khác biệt thiết kế đó.", "",
        "**V6 giảm dự báo trả đủ quá cao ở dài hạn.** Gap = dự báo − thực tế, đơn vị điểm phần trăm.", "",
        "| Ngày | Paid thực tế | Khánh dự báo | V6 dự báo | Gap Khánh → V6, điểm % |", "|---|---:|---:|---:|---:|", ]
    for day in protocol["days"]:
        a, b = metric("khanh_refit",day), metric("v6_final",day)
        lines.append(f"| {day} | {pct(b.actual_paid)} | {pct(a.pred_paid)} | {pct(b.pred_paid)} | {number(a.paid_gap*100,2)} → {number(b.paid_gap*100,2)} |")
    lines += ["", "Ở 365 ngày, tỷ lệ Paid thực tế trung bình khoảng 85%; Khánh dự báo gần 95%, V6 gần 87%. V6 giảm mức kỳ vọng trả đủ quá cao, đặc biệt ở phần đuôi.", "",
        "**Độ ổn định theo World.** Delta = Brier V6 − Khánh; âm có lợi cho V6. CI bootstrap ghép cặp 1.000 lần theo công ty trong từng World.", "",
        "| World | Anchor | Giảm Brier chính 28/91 | CI 95% delta chính | Giảm Brier 365 | CI 95% delta 365 |", "|---|---:|---:|---:|---:|---:|", ]
    for entry in protocol["entries"]:
        world = entry["name"]
        row = primary[primary.world == world].iloc[0]
        a = scores[(scores.world == world) & (scores.model == "khanh_refit") & (scores.day == 365)].iloc[0]
        b = scores[(scores.world == world) & (scores.model == "v6_final") & (scores.day == 365)].iloc[0]
        bound = bootstrap[(bootstrap.world == world) & (bootstrap.day == 365)].iloc[0]
        label = world.removeprefix("v4_shortpay_4shock_20261028_").replace("v6_holdout_20261101_", "holdout_")
        lines.append(f"| {label} | {int(row.n):,}".replace(",", ".") + f" | {number(row.improvement_pct,2)}% | {ci(row.ci_low,row.ci_high)} | {number(100*(1-b.paid_brier/a.paid_brier),2)}% | {ci(bound.ci_low,bound.ci_high)} |")
    lines += ["", f"Delta chính chung **{number(p['delta_vs_khanh'])}**, CI 95% **{ci(p['ci_low'],p['ci_high'])}**, không chứa 0. V6 có điểm chính tốt hơn ở 5/6 World; `validation_001` xấu hơn nhẹ khoảng 0,17%. Bốn CI chính riêng theo World còn chứa 0. Ở 365 ngày cả sáu CI đều dưới 0. CI chỉ đo bất định qua công ty trong các World cố định, chưa bao gồm nền kinh tế mới hoặc nhiều seed train.", "",
        "**Cải thiện theo nhóm quá hạn tại cutoff.** Phân tích hồi cứu, trung bình World bằng trọng số trong từng nhóm; chưa có CI slice và không dùng chọn model.", "",
        "| Quá hạn | Anchor | Giảm Brier chính | Giảm Brier 365 |", "|---|---:|---:|---:|", ]
    for key,label in {"not_overdue":"Chưa quá hạn", "1_30":"1–30 ngày", "31_90":"31–90 ngày", "91_180":"91–180 ngày", "over_180":"Trên 180 ngày"}.items():
        row = slices[(slices.dimension == "overdue_group") & (slices.group == key)].iloc[0]
        lines.append(f"| {label} | {int(row.n):,}".replace(",", ".") + f" | {number(row.primary_improvement_pct,2)}% | {number(row.brier365_improvement_pct,2)}% |")
    lines += ["", "Lợi thế dài hạn lớn hơn ở nhóm quá hạn lâu. Đây là kết quả mô tả của hai phiên bản; chưa tách riêng tác động của competing risks, feature hay tham số và chưa đối chiếu với cure T2.", "",
        "**Phân vị thời điểm trả đủ.** Mục tiêu đánh giá là `min(thời gian tới trả đủ, 120 ngày)`, gồm cả hóa đơn không trả. Trung bình bằng trọng số World.", "",
        "| Chỉ số | T1 Khánh | T1 v6 | Cải thiện |", "|---|---:|---:|---:|",
        f"| Pinball Q10/Q50/Q90 | {number(old_q.restricted_pinball120,4)} | {number(new_q.restricted_pinball120,4)} | Giảm {number(q_reduction,2)}% |",
        f"| MAE median, ngày | {number(old_q.restricted_median_mae120,4)} | {number(new_q.restricted_median_mae120,4)} | Giảm {number(mae_reduction,4)} ngày |", "",
        "Cải thiện về ngày trả cụ thể còn nhỏ. Hóa đơn không trả có giá trị 120 trong mục tiêu giới hạn, không được coi là thực sự trả ngày 120. Phân vị V6 chưa đạt được giữ trạng thái; khi chấm mục tiêu giới hạn thì quy về giới hạn. Không suy ra MAE ngày trả thật chưa bị chặn hoặc chất lượng Q90 dài hạn.", "",
        "**Giới hạn của kết luận.**", "",
        "- Đối chứng là bản mặc định từ mã Khánh tái train trên cùng fit; chưa phải booster lịch sử hoặc toàn bộ pipeline tuned/BLEND/CQR. Các feature chung dùng builder hiện tại, không phát lại toàn bộ ingest cũ.",
        "- Sáu World đều synthetic và đã xem: đây là benchmark hồi cứu, chưa chứng minh ưu thế trên SME thật. Ngành/ledger dùng quy trình quan sát synthetic có ngày biết/độ trễ; chưa phải dữ liệu doanh nghiệp thật đã xác nhận.",
        "- Phạm vi đối chiếu này là Paid và phân vị thời điểm trả đủ. Không suy kết quả sang chất lượng tiền thu hoặc kết luận thắng pipeline T1 + T2 cũ về Write-off.", "",
        "**Kết luận trao đổi với Khánh:** V6 cải thiện nhiệm vụ chung xác suất trả đủ, rõ nhất ở dài hạn và nợ quá hạn lâu. Ngắn hạn và phân vị ngày trả tăng ít hơn; calibration 28 ngày cùng một World vẫn có điểm yếu. Các mức cải thiện trên áp dụng cho đúng hai phiên bản được định nghĩa trong báo cáo.", "",
        "**Bằng chứng:** 70 kiểm thử qua; 144 file được bảo vệ giữ nguyên hash trong lần chấm; các chỉ số Paid tính lại từ dự báo lưu có sai khác 0. Bản gửi này chỉ lọc và trình bày lại kết quả hai model, không chạy dự báo/train lại.", "",
        f"Nguồn: [tóm tắt]({rel}comparison_summary.json), [protocol đối chiếu]({rel}comparison_protocol.json), [điểm theo World]({rel}scores.csv), [điểm tổng hợp]({rel}aggregate_scores.csv), [CI chính]({rel}primary_by_world.csv), [CI từng chân trời]({rel}bootstrap.csv), [phân vị]({rel}quantiles_restricted120.csv), [phân nhóm]({rel}slices_equal_world.csv), [kiểm tra bản gửi]({rel}verification.json).", "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    if any(sha(ROOT / path) != digest for path,digest in source_hashes.items()):
        raise ValueError("Original benchmark results changed")
    write_json(out / "verification.json", {"source_results_sha256":source_hashes,
        "original_results_unchanged":True, "only_two_models_in_score_tables":True,
        "report_sha256":sha(report), "history_path":str(history.relative_to(ROOT)),
        "history_sha256":sha(history), "new_training_or_prediction":False,
        "prior_tests":review["tests"], "prior_protected_files_unchanged":144})
    share = out / "share"
    share.mkdir()
    text = report.read_text(encoding="utf-8")
    for name in out.glob("*.csv"):
        shutil.copy2(name,share/name.name)
    for name in out.glob("*.json"):
        shutil.copy2(name,share/name.name)
    text = re.sub(r"(\[[^\]]+\])\("+re.escape(rel)+r"([^)]+)\)",r"\1(\2)",text)
    (share / "T1_V6_VS_KHANH.md").write_text(text, encoding="utf-8", newline="\n")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)",text):
        if not (share/target).is_file():
            raise ValueError("Broken standalone report link")
    (share/"README.md").write_text("# So sánh T1 Khánh và T1 v6\n\nMở T1_V6_VS_KHANH.md trước.\n\nGói chỉ chứa báo cáo và bảng số của hai mô hình: T1 Khánh mặc định tái train và V6 ngành/ledger ngày 05/11. Trọng tâm là Paid và phân vị trả đủ. Không kèm so sánh V6 cũ, unified, cash head lịch sử hoặc kế hoạch phát triển. Chạy lại benchmark cần repo và artifact gốc; gói này không chứa weights/raw World.\n",encoding="utf-8")
    manifest = {f.name:sha(f) for f in share.iterdir() if f.is_file()}
    write_json(share/"MANIFEST.json",manifest)
    bundle = out/"T1_V6_VS_KHANH_ONLY_20261105.zip"
    with zipfile.ZipFile(bundle,"x",zipfile.ZIP_DEFLATED) as z:
        for f in sorted(share.iterdir()):
            z.write(f,f.name)
    with zipfile.ZipFile(bundle) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
    write_json(out/"package_review.json", {"report_sha256":sha(report), "bundle_sha256":sha(bundle),
        "bundle_files":len(manifest)+1,"bundle_bytes":bundle.stat().st_size,"only_two_models":True})
    print(json.dumps({"report":str(report.relative_to(ROOT)),"bundle":str(bundle.relative_to(ROOT)),"files":len(manifest)+1,"bytes":bundle.stat().st_size},indent=2))


if __name__ == "__main__":
    main()
