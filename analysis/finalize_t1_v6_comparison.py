"""Verify the fixed-candidate evaluation and build the Vietnamese handoff report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

import lightgbm as lgb
import numpy as np
import pandas as pd

from analysis.benchmark_t1_khanh_vs_v6 import probability_score, sha, write_json
from analysis.benchmark_t1_v6_final_vs_khanh import BASE, DEFAULT, KEYS, PRACTICAL, ROOT


def number(value, digits=6):
    return f"{value:.{digits}f}".replace(".", ",")


def pct(value, digits=2):
    return number(100 * value, digits) + "%"


def ci(low, high):
    return f"[{number(low)}; {number(high)}]"


def main():
    out = DEFAULT
    protocol = json.loads((out / "protocol.lock.json").read_text(encoding="utf-8"))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    verification = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    if sha(ROOT / "analysis/benchmark_t1_v6_final_vs_khanh.py") != protocol["script_sha256"]:
        raise ValueError("Evaluation script changed after protocol lock")
    code_lock = json.loads((PRACTICAL / "code.lock.json").read_text(encoding="utf-8"))
    for relative, digest in code_lock.items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Observation/model code differs from the prior experiment: {relative}")
    for relative, digest in protocol["protected"].items():
        if sha(ROOT / relative) != digest:
            raise ValueError(f"Protected input changed: {relative}")
    for relative, digest in verification["result_sha256"].items():
        if sha(out / relative) != digest:
            raise ValueError(f"Evaluation output changed: {relative}")
    scores = pd.read_csv(out / "scores.csv", float_precision="round_trip")
    aggregate = pd.read_csv(out / "aggregate_scores.csv", float_precision="round_trip")
    primary = pd.read_csv(out / "primary_by_world.csv", float_precision="round_trip")
    bootstrap = pd.read_csv(out / "bootstrap.csv", float_precision="round_trip")
    slices = pd.read_csv(out / "slices_equal_world.csv", dtype={"group": str})
    quantiles = pd.read_csv(out / "quantiles_restricted120.csv")
    maximum = 0.
    for entry in protocol["entries"]:
        world = entry["name"]
        prediction = pd.read_parquet(out / "predictions" / f"{world}.parquet")
        old = pd.read_parquet(BASE / "predictions" / f"{world}.parquet")
        if not prediction[list(old)].equals(old):
            raise ValueError("Reused baseline predictions were changed")
        features = pd.read_parquet(out / "features" / f"{world}.parquet")
        if not features[KEYS].equals(prediction[KEYS]) or features.filter(like="macro_").shape[1]:
            raise ValueError("Feature alignment or macro exclusion failed")
        for day in protocol["days"]:
            truth = ((prediction.cause == 1) & (prediction.time_days <= day)).to_numpy(float)
            for name, prefix in (("khanh_refit", "khanh_refit"), ("v6_original", "v6"), ("v6_final", "v6_final")):
                expected = scores[(scores.world == world) & (scores.model == name) & (scores.day == day)].iloc[0]
                result = probability_score(truth, prediction[f"{prefix}_paid_{day}"].to_numpy())
                for field in result:
                    maximum = max(maximum, abs(result[field] - expected[field]))
            state_sum = prediction[[f"v6_final_{s}_{day}" for s in ("open", "paid", "writeoff")]].sum(axis=1)
            if not np.allclose(state_sum, 1, atol=3e-6):
                raise ValueError("Incoherent competing-risk distribution")
        if (np.diff(prediction[[f"v6_final_paid_{d}" for d in protocol["days"]]], axis=1) < -1e-7).any():
            raise ValueError("Non-monotone Paid CIF")
    if maximum > 1e-12:
        raise ValueError("Saved scores disagree with predictions")
    test_source = Path(str(out) + "_tests.xml")
    tests = ET.parse(test_source).getroot()
    test_info = {key: sum(int(s.get(key, 0)) for s in tests.iter("testsuite")) for key in ("tests", "failures", "errors", "skipped")}
    if test_info["failures"] or test_info["errors"]:
        raise ValueError("Tests failed")
    shutil.copy2(test_source, out / "tests.xml")
    with zipfile.ZipFile(out / "source_snapshot.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        files = [ROOT / "analysis/benchmark_t1_v6_final_vs_khanh.py", Path(__file__),
                 ROOT / "analysis/benchmark_t1_khanh_vs_v6.py", ROOT / "tests/test_t1_v6_final_benchmark.py"]
        for relative in protocol["protected"]:
            if relative.endswith(".py") and not relative.startswith("outputs/"):
                files.append(ROOT / relative)
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())

    def metric(model, day):
        return aggregate[(aggregate.model == model) & (aggregate.day == day)].iloc[0]

    p = summary["primary"]
    a365, b365 = metric("khanh_refit", 365), metric("v6_final", 365)
    improvement365 = 100 * (1 - b365.paid_brier / a365.paid_brier)
    candidate = lgb.Booster(model_file=str(PRACTICAL / "models/both.txt"))
    candidate_bytes = (PRACTICAL / "models/both.txt").stat().st_size
    report = ROOT / "docs/03_Evaluation/T1_V6_PROGRESS_VS_KHANH_2026-11-05.md"
    history = report.with_name("T1_V6_PROGRESS_VS_KHANH_V6_ORIGINAL_DETAIL_2026-11-05.md")
    if not history.exists():
        with history.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("<!-- Lịch sử: đối chiếu V6 gốc 01/11, trước khi chốt ứng viên ngành/ledger 05/11. -->\n\n" + report.read_text(encoding="utf-8"))
    rel = "../../outputs/analysis/t1_v6_final_vs_khanh_20261105/"
    oldrel = "../../outputs/analysis/t1_khanh_vs_v6_20261105/"
    lines = [
        "# T1 của Khánh và T1 v6 ngày 05/11 — báo cáo chốt nghiên cứu", "",
        "**Ngày 05/11/2026. Bản V6 hiện tại là V6 + ngành + hành vi ledger (`both`), 93 feature snapshot. Đã chấm trên cùng 65.221 anchor thuộc sáu World với baseline Khánh đã lưu. Không train hoặc hiệu chỉnh trong lần này.**", "",
        f"**Kết luận: V6 ngày 05/11 cải thiện dự báo xác suất trả đủ so với `HazardGBM` mặc định từ mã Khánh được tái train trên cùng tập fit.** Brier Paid chính 28/91 ngày giảm **{number(p['improvement_vs_khanh_pct'], 2)}%**, thấp hơn ở **{summary['worlds_final_better_than_khanh']}/6 World**; Brier Paid 365 ngày giảm **{number(improvement365, 2)}%**. Các mức này thuộc đúng artifact ngày 05/11, thay cho số của V6 gốc trong phần kết luận hiện hành.", "",
        "**Đã chốt V6 ngày 05/11 làm ứng viên nghiên cứu hiện tại**, giữ nguyên weights, 160 vòng, identity calibration và quy trình feature. Quyết định được ghi trước khi đọc kết quả lần chấm này, kế thừa nhánh đã chọn trên nguồn. Tạm dừng thêm feature/kiến trúc; bước tiếp theo là kiểm đầu vào và tích hợp thử nghiệm. Đây chưa phải nghiệm thu hoặc kích hoạt dịch vụ.", "",
        f"Bản chốt có SHA-256 `{summary['candidate_sha256']}`. [Manifest chốt nghiên cứu]({rel}research_candidate.lock.json) ghi model, thứ tự feature, trạng thái và phạm vi sử dụng.", "",
        "Đối chứng Khánh là bản mặc định tại commit `70c0ceb` ngày 24/10/2026, đã tái train trong benchmark trước. Không có booster lịch sử đúng mốc được xác nhận; kết luận chưa bao quát cấu hình tuned, BLEND/CQR hoặc pipeline T1 + T2/T6 đầy đủ của Khánh.", "",
        "**Kết quả theo nhiệm vụ.**", "",
        "| Nhiệm vụ | Kết quả | Đánh giá |", "|---|---|---|",
        f"| Xác suất trả đủ 28/91 ngày | Brier {number(p['khanh'])} → {number(p['v6_final'])}; giảm {number(p['improvement_vs_khanh_pct'],2)}% | Cải thiện trung bình; xem CI và từng World bên dưới |",
        f"| Xác suất trả đủ 365 ngày | Brier giảm {number(improvement365,2)}%; gap Paid {number(a365.paid_gap*100,2)} → {number(b365.paid_gap*100,2)} điểm % | Lợi thế dài hạn rõ hơn ngắn hạn trong benchmark |",
        "| Thời điểm trả đủ | Chấm lại phân vị của bản 05/11 trên mục tiêu giới hạn 120 ngày | Chỉ kết luận trong mục tiêu này |",
        "| Tiền thu | Không có cash head mới cho nhánh 05/11 | Bảng tiền thu bên dưới là lịch sử V6 gốc, không gán cho bản mới |",
        "| Write-off so với T2 cũ | Không có đối chứng cùng định nghĩa | Chưa kết luận thắng pipeline T1 + T2 cũ |", "",
        "**Hai mô hình được chấm.**", "",
        "| Thành phần | T1 Khánh tái train | V6 ngày 05/11 |", "|---|---|---|",
        "| Estimator | HazardGBM nhị phân Paid | Competing risks Open/Paid/Write-off |",
        "| Chân trời học | 13 tuần; sau đó đuôi hình học, hazard kẹp [0,02; 0,6] | 53 tuần |",
        "| Feature snapshot + tuần | 46 + 7 | 93 + 7 |",
        "| Số vòng / leaves | 600 / 63 | 160 / 31 |",
        "| Learning rate / L2 | 0,05 / 5 | 0,05 / 8 |",
        "| Feature fraction / bagging fraction | 0,80 / 0,80 | 0,85 / 0,85 |",
        "| Seed | 7 | 20261101 |",
        "| Hàng risk set fit | 1.561.446 | 2.589.709 |",
        "| Risk set | Write-off tiếp tục là không Paid trong nhãn T1 cũ | Dừng ở mọi cause đóng |",
        "| Calibration | Mặc định; không thêm BLEND/CQR | Identity |",
        f"| Số cây / file model | 600 / 4,05 MiB | {candidate.num_trees()} / {number(candidate_bytes/1024**2,2)} MiB |", "",
        "160 vòng đa lớp tạo 480 cây cho ba lớp có support; không so số vòng như thể cả hai đều là binary. File nhỏ hơn không chứng minh latency/RAM thấp hơn: lần này chưa đo hiệu năng. Credit-note-only không có support trong train.", "",
        "So với Khánh, V6 gốc thêm 18 feature về lịch sử Write-off, cơ cấu quá hạn, thu từng phần và điều chỉnh dư nợ. Bản 05/11 thêm 14 one-hot ngành mua/bán có ngày biết và 15 feature biến động ledger as-of. Tổng cộng 47 feature snapshot bổ sung; không dùng năm `macro_credit_*` giả lập. Lịch sử khách, trend và lịch thanh toán đã có trong T1 Khánh.", "",
        "**Điều kiện đối chứng.** Hai bên dùng đúng 200.000 snapshot fit, 128 công ty nguồn, 100.028 hóa đơn riêng biệt. Thứ tự và 46 feature chung giống nhau theo builder hiện tại; đây không phải phát lại toàn bộ ingest lịch sử của Khánh. Bản 05/11 giữ nguyên tập fit/risk set/cấu hình V6, chỉ thêm whitelist ngành/ledger đã định nghĩa.", "",
        "65.221 anchor gồm 25.162 validation, 20.336 test và 19.723 holdout của lần 01/11; mỗi World 40 công ty. Mỗi hóa đơn có một anchor đầu tiên đủ điều kiện, cutoff 01/07–16/12/2024, đủ follow-up 365 ngày. Đã đối chiếu nguyên thứ tự khóa, nhãn, thời gian theo dõi và dư nợ với dự báo cũ. Baseline Khánh được dùng lại nguyên vẹn, không fit lại.", "",
        "Chỉ số chính kế thừa benchmark đã khóa: trung bình Brier Paid 28/91 ngày trong từng World, sau đó trung bình sáu World bằng trọng số. Brier/ECE nhỏ hơn là tốt hơn; giảm % là giảm sai số tương đối. Paid nghĩa là trả đủ, không phải chỉ có thu từng phần. Không gán Write-off Khánh bằng 0 để chấm joint Brier.", "",
        "Tất cả sáu World đều đã xem: đây là đối chứng hồi cứu, không phải fresh confirmation mới hoặc bằng chứng trên SME thật. Không chọn lại ứng viên theo điểm các World này.", "",
        "**Xác suất Paid theo sáu chân trời, trung bình World bằng trọng số.**", "",
        "| Ngày | Brier Khánh | Brier V6 05/11 | V6 giảm Brier | ECE Khánh → V6 |", "|---|---:|---:|---:|---:|",
    ]
    for day in protocol["days"]:
        old, new = metric("khanh_refit", day), metric("v6_final", day)
        lines.append(f"| {day} | {number(old.paid_brier)} | {number(new.paid_brier)} | {number(100*(1-new.paid_brier/old.paid_brier),2)}% | {number(old.paid_ece,5)} → {number(new.paid_ece,5)} |")
    lines += ["", "Sau 91 ngày Khánh ngoại suy đuôi, V6 tiếp tục dùng hazard được học. Lợi thế dài hạn phản ánh toàn bộ thay đổi phiên bản, chưa phân rã riêng đóng góp của competing risks, feature hay regularization.", "",
        "| Ngày | Paid thực tế | Khánh dự báo | V6 dự báo | Gap Khánh → V6, điểm % |", "|---|---:|---:|---:|---:|", ]
    for day in protocol["days"]:
        old, new = metric("khanh_refit", day), metric("v6_final", day)
        lines.append(f"| {day} | {pct(new.actual_paid)} | {pct(old.pred_paid)} | {pct(new.pred_paid)} | {number(old.paid_gap*100,2)} → {number(new.paid_gap*100,2)} |")
    lines += ["", "**Kết quả theo World và bất định.** Delta = Brier V6 05/11 − Khánh; âm có lợi cho V6. Bootstrap ghép cặp 1.000 lần theo công ty trong từng World.", "",
        "| World | Anchor | Giảm Brier chính | CI 95% delta chính | Giảm Brier 365 | CI 95% delta 365 |", "|---|---:|---:|---:|---:|---:|", ]
    for entry in protocol["entries"]:
        world = entry["name"]
        row = primary[primary.world == world].iloc[0]
        old = scores[(scores.world == world) & (scores.model == "khanh_refit") & (scores.day == 365)].iloc[0]
        new = scores[(scores.world == world) & (scores.model == "v6_final") & (scores.day == 365)].iloc[0]
        bound = bootstrap[(bootstrap.world == world) & (bootstrap.day == 365)].iloc[0]
        label = world.removeprefix("v4_shortpay_4shock_20261028_").replace("v6_holdout_20261101_", "holdout_")
        lines.append(f"| {label} | {int(row.n):,}".replace(",", ".") + f" | {number(row.improvement_pct,2)}% | {ci(row.ci_low,row.ci_high)} | {number(100*(1-new.paid_brier/old.paid_brier),2)}% | {ci(bound.ci_low,bound.ci_high)} |")
    lines += ["", f"Delta chính chung là **{number(p['delta_vs_khanh'])}**, CI 95% **{ci(p['ci_low'],p['ci_high'])}**. CI này chỉ đo bất định qua công ty trong sáu World cố định, không bao gồm nền kinh tế mới hoặc nhiều seed train. Điểm tốt hơn ở một World không đồng nghĩa CI riêng của World đó loại trừ 0.", "",
        "**Phần bổ sung ngày 05/11 so với V6 gốc 01/11.**", "",
        f"Trên cùng benchmark này, Brier Paid chính là **{number(p['v6_original'])} → {number(p['v6_final'])}**, **{'giảm' if p['improvement_vs_original_pct'] >= 0 else 'tăng'} {number(abs(p['improvement_vs_original_pct']),2)}%**; delta = **{number(p['delta_vs_original'])}**, CI 95% **{ci(p['vs_original_ci_low'],p['vs_original_ci_high'])}**. Đây là đối chiếu mô tả sau khi đã chọn ứng viên, không dùng để chọn lại bản chốt. Tiêu chí chọn nhánh trước đó là joint/Write-off Brier 365 ngày trên nguồn với giới hạn Paid ngắn hạn; không phải tối thiểu hóa riêng Paid Brier ở benchmark này.", "",
        "Trong lần P0–P4 trước, nhánh `both` đã được chọn bằng 10.666 anchor nguồn trước khi sinh bốn fresh World. Joint Brier 365 giảm 0,49% trên fresh; cả bốn CI theo công ty chứa 0, chỉ 1/4 World qua toàn bộ tiêu chí nghiên cứu. Vì vậy việc chốt bản hiện tại không đồng nghĩa phần bổ sung có lợi chắc chắn hoặc đã giải quyết distribution shift.", "",
        "**Phân nhóm hồi cứu theo quá hạn.** Trung bình World bằng trọng số trong mỗi nhóm; không phải tiêu chí chọn model hoặc kết luận nhân quả, chưa có CI slice.", "",
        "| Quá hạn tại cutoff | Anchor | Giảm Brier chính | Giảm Brier 365 |", "|---|---:|---:|---:|", ]
    labels = {"not_overdue": "Chưa quá hạn", "1_30": "1–30 ngày", "31_90": "31–90 ngày", "91_180": "91–180 ngày", "over_180": "Trên 180 ngày"}
    for key, label in labels.items():
        row = slices[(slices.dimension == "overdue_group") & (slices.group == key)].iloc[0]
        lines.append(f"| {label} | {int(row.n):,}".replace(",", ".") + f" | {number(row.primary_improvement_pct,2)}% | {number(row.brier365_improvement_pct,2)}% |")
    lines += ["", "Số âm ở cột giảm sai số nghĩa là V6 xấu hơn. Bảng tháng và kết quả đầy đủ giữ trong CSV; các nhóm phụ thuộc nhau, không dùng để tối ưu theo tháng/tuổi nợ đã xem.", "",
        "**Phân vị thời điểm trả đủ.** Chấm mục tiêu `min(thời gian tới trả đủ, 120 ngày)`, gồm cả hóa đơn không trả. Trung bình bằng trọng số World.", "",
        "| Model | Pinball Q10/Q50/Q90 | MAE median, ngày |", "|---|---:|---:|", ]
    for label, title in (("khanh_refit", "T1 Khánh"), ("v6_original", "V6 gốc 01/11, đối chiếu phụ"), ("v6_final", "V6 hiện tại 05/11")):
        row = quantiles[quantiles.model == label].select_dtypes(include="number").mean()
        lines.append(f"| {title} | {number(row.restricted_pinball120,4)} | {number(row.restricted_median_mae120,4)} |")
    lines += ["", "Hóa đơn không trả có giá trị 120 trong mục tiêu giới hạn, không coi là đã trả thật ngày 120. Phân vị V6 chưa đạt được giữ trạng thái; khi chấm mục tiêu giới hạn thì quy về giới hạn. Không suy từ đây ra MAE ngày trả thật chưa bị chặn hoặc chất lượng Q90 dài hạn.", "",
        "**Tiền thu — kết quả lịch sử V6 gốc 01/11, không phải cash head của bản 05/11.** Lần này chỉ đánh giá hazard/phân vị mới. Cash head cũ không được train hoặc chấm lại với 93 feature. Đối chứng Khánh là `dư nợ × P(Paid trước h)`, không phải toàn bộ T6.", "",
        "| Ngày | WAPE công ty Khánh → V6 gốc | WAPE hóa đơn Khánh → V6 gốc |", "|---|---:|---:|",
        "| 28 | 12,03% → 12,38% | 65,78% → 78,49% |", "| 91 | 8,21% → 6,56% | 30,73% → 32,41% |",
        "| 180 | 6,02% → 4,98% | 17,84% → 20,56% |", "| 365 | 7,30% → 5,07% | 12,22% → 15,98% |", "",
        "WAPE gộp theo tổng tiền thực thu, khác cách lấy trung bình World của bảng xác suất. Sai số có thể triệt tiêu khi cộng theo công ty; kết quả không ủng hộ dùng cash head cũ làm mặc định cho từng hóa đơn. Chưa có CI WAPE.", "",
        "**Giới hạn thực tế và quyết định tiếp theo.**", "",
        "Feature ngành/ledger mới có known_at, missing/coverage và giới hạn tenant. Lần benchmark vẫn dùng lớp quan sát ERP synthetic: ngành là customer-master giả lập theo quý, coverage 75%, trễ 14 ngày; ledger có sai số phân bổ và trễ tiếp nhận. 64 feature V6 gốc vẫn giữ giả định synthetic về lịch sử/đóng nợ/liên kết tiền. Chưa thể gọi toàn bộ đầu vào là đã kiểm chứng trên doanh nghiệp thật.", "",
        f"Riêng test_000, Write-off 365 ngày của bản mới là **{pct(scores[(scores.world.str.endswith('test_000')) & (scores.model == 'v6_final') & (scores.day == 365)].iloc[0].pred_writeoff)}**, thực tế **{pct(scores[(scores.world.str.endswith('test_000')) & (scores.model == 'v6_final') & (scores.day == 365)].iloc[0].actual_writeoff)}**. Thắng Paid so với T1 không tự giải quyết calibration Write-off. Không so trực tiếp cure T2 với Write-off hữu hạn.", "",
        "Benchmark unified v2 trước đây dùng V6 gốc 01/11, chưa dùng nhánh 93 feature này. Không chuyển điểm CRPS/coverage cũ sang bản 05/11. Việc chốt nghiên cứu hiện tại không thay cổng sản phẩm hoặc model dịch vụ.", "",
        "Công việc tiếp theo đã thu hẹp: **giữ nguyên model hiện tại; kiểm toàn bộ nguồn/thời điểm biết của đầu vào; hoàn thiện adapter và tích hợp thử nghiệm**. Calibration, hazard theo thời gian và cash head là hướng dự phòng khi phép đo sử dụng chỉ ra lỗi cụ thể, không phải ba vòng nâng cấp bắt buộc trước khi kết thúc nghiên cứu này.", "",
        "**Bằng chứng và tái lập.**", "",
        f"**{test_info['tests']} kiểm thử qua**, gồm chặn lệch khóa/thứ tự/nhãn/dư nợ và hồi quy feature/risk set. **{verification['protected_files_checked']} file được bảo vệ giữ nguyên hash**. Các chỉ số Paid được tính độc lập lại từ dự báo lưu, sai khác lớn nhất **{maximum:.3g}**. Không fit, sinh World hoặc hiệu chỉnh; baseline Khánh và model V6 giữ nguyên.", "",
        "```powershell", ".\\.venv\\Scripts\\python.exe -X utf8 -B -u -m analysis.benchmark_t1_v6_final_vs_khanh --output outputs/analysis/t1_v6_final_vs_khanh_rerun",
        ".\\.venv\\Scripts\\python.exe -X utf8 -B -m pytest tests/test_t1_v6_final_benchmark.py tests/test_t1_khanh_benchmark.py tests/test_t1_v6_practical.py tests/test_t1_practical_context.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider", "```", "",
        "Thư mục output mới phải chưa tồn tại. Script đọc weights, baseline và bảng quan sát theo thiết kế đã khóa; không retrain. Lặp lại cùng seed/World không trở thành một test fresh mới.", "",
        f"Nguồn: [protocol lần chấm]({rel}protocol.lock.json), [summary]({rel}summary.json), [điểm từng World]({rel}scores.csv), [điểm tổng hợp]({rel}aggregate_scores.csv), [CI chính]({rel}primary_by_world.csv), [CI từng chân trời]({rel}bootstrap.csv), [phân nhóm]({rel}slices_equal_world.csv), [phân vị]({rel}quantiles_restricted120.csv), [missingness]({rel}feature_missingness.csv), [verification]({rel}verification.json), [source snapshot]({rel}source_snapshot.zip), [baseline gốc]({oldrel}protocol.lock.json), [cash lịch sử]({oldrel}cash_scores.csv), [lựa chọn trên nguồn](../../outputs/data/t1_v6_practical_20261105_r2/final_selection.lock.json), [fresh trước đó](../../outputs/data/t1_v6_practical_20261105_r2/fresh_scores.csv).", "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    # Standalone evidence bundle; retain older report/bundle unchanged.
    share = out / "share"
    share.mkdir(exist_ok=False)
    pattern = re.compile(r"(\[[^\]]+\])\(([^)]+)\)")
    text = report.read_text(encoding="utf-8")
    links = []
    def copy_link(match):
        source = (report.parent / match.group(2)).resolve()
        if not source.is_file():
            raise ValueError(f"Broken report link: {source}")
        target = Path("evidence") / source.relative_to(ROOT)
        (share / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, share / target)
        links.append(target.as_posix())
        return match.group(1) + "(" + target.as_posix() + ")"
    standalone = pattern.sub(copy_link, text)
    for source in (BASE / "source_snapshot.zip", PRACTICAL / "source_snapshot.zip",
                   PRACTICAL / "models/both.json", PRACTICAL / "code.lock.json", out / "tests.xml"):
        target = share / "evidence" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (share / "T1_V6_SO_SANH_GUI_KHANH_20261105_FINAL.md").write_text(standalone, encoding="utf-8", newline="\n")
    (share / "README.md").write_text(
        "# Báo cáo V6 ngày 05/11 để gửi Khánh\n\nMở T1_V6_SO_SANH_GUI_KHANH_20261105_FINAL.md.\n\n"
        "Bản được chấm là V6 + ngành + ledger (93 feature), so với HazardGBM mặc định từ mã Khánh tái train. "
        "Bản chốt là ứng viên nghiên cứu, chưa kích hoạt dịch vụ. Các liên kết trong báo cáo trỏ tới bằng chứng kèm theo. "
        "Gói không chứa raw World hoặc weights; chạy lại cần repo và artifact gốc. Cash head trong báo cáo thuộc V6 gốc 01/11.\n",
        encoding="utf-8")
    manifest = {path.relative_to(share).as_posix(): sha(path) for path in share.rglob("*") if path.is_file()}
    write_json(share / "MANIFEST.json", manifest)
    bundle = out / "T1_V6_SO_SANH_GUI_KHANH_20261105_FINAL.zip"
    with zipfile.ZipFile(bundle, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(share.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(share).as_posix())
    with zipfile.ZipFile(bundle) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt handoff bundle")
        for relative, digest in manifest.items():
            if hashlib.sha256(archive.read(relative)).hexdigest() != digest:
                raise ValueError("Bundle differs from its file manifest")
    write_json(out / "report_review.json", {"report_sha256": sha(report), "tests": test_info,
        "maximum_recomputed_paid_score_difference": maximum,
        "observation_code_matches_prior_code_lock": True,
        "protected_files_checked": verification["protected_files_checked"], "changed_protected_files": [],
        "bundle_sha256": sha(bundle), "bundle_bytes": bundle.stat().st_size,
        "direct_report_links_verified": len(links), "manifest_files_verified": len(manifest)})
    print(json.dumps({"primary": p, "brier365_improvement_pct": improvement365,
                      "report": str(report.relative_to(ROOT)), "bundle": str(bundle.relative_to(ROOT)), "tests": test_info}, indent=2))


if __name__ == "__main__":
    main()
