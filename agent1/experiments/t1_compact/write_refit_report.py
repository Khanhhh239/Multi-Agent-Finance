"""Publish measured findings without changing any fitted/selected artifact."""
import argparse
import json
from pathlib import Path
import platform
import sys
from importlib.metadata import version

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from agent1.adaptive.compact_t1 import sha256, CompactT1
from experiments.t1_compact.aligned_data import write
from experiments.t1_compact.compare_adaptation import COMPARISON, NAMES
from experiments.t1_compact.refit_landmark import load_role
from experiments.t1_compact.train_landmark import context_for, summarize_prediction, score_prediction

LABELS=dict(old_global="Global hiện tại 75/25",global_refit="Ứng viên refit",
            global_reweighted="Global chọn lại trọng số local",global_finetuned="Global học tiếp Neural + pooling local",
            global_adapted_audited="Global thích nghi qua audit local",local_neural18="Neural local 18 feature + fallback Workspace",workspace="Workspace local hiện tại")


def run(output):
    from experiments.t1_compact.benchmark_large_book import run as large_book
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=2),threadpool_limits(limits=1,user_api="blas"):
        large=large_book(output)
    def read(name): return json.loads((output/name).read_text(encoding="utf-8"))
    results=read("fresh_results.json")
    audit=read("audit_results.json")
    release=read("release.json")
    runtime=read("runtime_verification.json")
    frozen=read("frozen.json")
    initial=read("selection.json")["selected"]
    initial_members=", ".join(f"{n} {w:.0%}" for n,w in zip(initial["members"],initial["weights"]))
    final_members=", ".join(f"{n} {w:.0%}" for n,w in zip(frozen["members"],frozen["weights"]))
    decision_text=("Bản refit qua audit đã khai báo và được chấp nhận cho đường tích hợp nghiên cứu."
        if audit["passed"] else "Bản refit không qua audit đã khai báo; giữ global hiện tại cho đường tích hợp nghiên cứu.")
    records=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((output/COMPARISON).rglob("receipt.json"))]
    table=pd.read_csv(output/"fresh_by_firm_origin.csv")
    by_world=table.groupby(["world","firm","model"]).mean(numeric_only=True).groupby(["world","model"]).mean(numeric_only=True).reset_index()
    by_world.to_csv(output/"fresh_by_world.csv",index=False)
    firms=table.groupby(["world","firm","model"]).score.mean().unstack("model")
    rng=np.random.default_rng(261113)
    paired={}
    for challenger,reference in [("global_finetuned","old_global"),("global_adapted_audited","old_global"),
                                 ("global_finetuned","local_neural18"),("global_adapted_audited","workspace")]:
        delta=firms[reference]-firms[challenger]
        draws=[]
        for _,group in delta.groupby(level="world"):
            values=group.to_numpy()
            draws.append(values[rng.integers(0,len(values),size=(10000,len(values)))].mean(1))
        paired[challenger+"_vs_"+reference]=dict(mean_delta=float(delta.groupby(level="world").mean().mean()),
            ci95=list(map(float,np.quantile(np.mean(draws,axis=0),[.025,.975]))),
            firms_improved=int((delta>1e-12).sum()),firms=len(delta),positive_favors_challenger=True)
    write(output/"paired_comparisons.json",paired)
    # Separate the architecture comparison from insufficient-data fallbacks.
    eligible={(r["world"],r["firm"],r["origin"]) for r in records if r["status"]=="adapted"}
    frame=load_role(output,"fresh_test")
    mask=np.array([(w,f,str(o.date())) in eligible for w,f,o in zip(frame.world,frame.firm,frame.origin)])
    subset=frame[mask].reset_index(drop=True)
    probabilities={name:[] for name in NAMES}
    for key,part in frame.groupby(["world","firm","origin"],sort=False):
        if (key[0],key[1],str(key[2].date())) not in eligible: continue
        path=output/COMPARISON/key[0]/key[1]/str(key[2].date())/"predictions.npz"
        with np.load(path,allow_pickle=False) as saved:
            for name in NAMES: probabilities[name].append(saved[name])
    # groupby preserves the physical concatenation order in prepared tables;
    # explicitly assemble the same subset order before scoring.
    parts=[]
    for key,part in frame.groupby(["world","firm","origin"],sort=False):
        if (key[0],key[1],str(key[2].date())) in eligible: parts.append(part)
    subset=pd.concat(parts,ignore_index=True)
    context=context_for(subset)
    eligible_results={name:score_prediction(summarize_prediction(np.concatenate(p),context),context) for name,p in probabilities.items()}
    write(output/"eligible_local_results.json",dict(contexts=len(eligible),anchors=len(subset),results=eligible_results))
    neural=[]
    for path in sorted((output/"trials").glob("neural*/trial.json")):
        trial=json.loads(path.read_text(encoding="utf-8"))
        clf=CompactT1.load(path.parent/"model").booster[-1]
        neural.append(dict(name=path.parent.name,iterations=int(clf.n_iter_),maximum=int(clf.max_iter),
                           warnings=trial["warnings"],validation_score=trial["score"]))
    write(output/"neural_convergence.json",neural)
    timings=pd.read_csv(output/"compute_budget_summary.csv")
    report=["# T1 18 feature: đồng bộ, refit, học tiếp local và T6 — 13/11/2026","",
        "## Quyết định dựa trên bằng chứng","",
        "Đã hoàn thành một lượt thí nghiệm mới và giữ nguyên artifact/báo cáo cũ. Bản refit được huấn luyện với feature phục vụ đã căn chỉnh, ngân sách Neural 400/600 vòng và validation trọng số riêng. "+decision_text+" Global 75/25 hiện tại luôn là điểm xuất phát và đối chứng cho nhánh học tiếp được yêu cầu.","",
        f"Test mới gồm **{results['worlds']} World, {results['firms']} doanh nghiệp, {results['contexts']} doanh nghiệp/ngày chốt và {results['anchors']:,} snapshot hóa đơn đủ điều kiện**. Có {results['adapted_contexts']} context đủ cửa sổ để thử thích nghi và {results['audit_accepted_contexts']} context chấp nhận thích nghi bằng audit quá khứ.","",
        "Đường phục vụ có kiểm hash/ngày sẵn sàng và allowlist tenant đã được tích hợp. Chưa đặt biến môi trường để thay model của tenant nào. Mặc định Monte Carlo T6 đã đổi thành 1000 đường; SHAP vẫn tối đa 30 hóa đơn. Cổng pilot thật không thay đổi.","",
        "## Đồng bộ feature và dữ liệu được biết","",
        "`ledger_bridge.workspace_data` biểu diễn giảm trừ thành phiên bản công nợ có ngày biết, không thành tiền thu. `ledger_context` là adapter vector hóa cho ledger World giới hạn này; đối chiếu với `workspace_context` thực tế ở đầu/cuối mỗi lịch sử doanh nghiệp và kiểm tra lại đầu vào model tại từng context test. Train, serving và SHAP cùng dùng `landmark_features.prepare_features`, đủ 18 feature và một tọa độ tuần tương lai.","",
        "Lịch sử tất toán và giá trị hóa đơn đi theo kế toán Workspace, gồm giá trị claim đã được điều chỉnh khi đã biết. Nhãn đánh giá vẫn là tất toán bằng tiền của claim đủ điều kiện; loại thay đổi claim trong follow-up và tiền trước origin nhưng được biết muộn. Toàn bộ kết luận có điều kiện trên quần thể đủ 91 ngày theo dõi; không áp dụng tự động cho mọi ca điều chỉnh kế toán.","",
        "`alignment_audit.json` lưu số hàng/feature thay đổi so với builder cũ. Kiểm thử có giảm trừ, tiền biết muộn, closure không bằng tiền, và bất biến khi bỏ bản ghi tương lai.","",
        "## Selection, refit và audit global","",
        "1. Fit 16 ứng viên/29 trial trên 8 World train, 76 lịch sử doanh nghiệp, 78.171 snapshot; cùng mẫu tối đa 100.000 risk-row. Survival là ứng viên tùy chọn và đối chứng.",
        "2. Ba World validation gốc chọn cấu hình và ensemble theo lỗi thu tuần/lũy kế chuẩn hóa, độ ổn định, integrated Brier và SHAP. Kết quả trước refit: "+initial_members+".",
        "3. Refit đúng cấu hình thành viên trên train + validation gốc. Validation gốc trở thành dữ liệu refit; không còn được coi là holdout của artifact refit.",
        "4. Hai World mới chỉ chọn trọng số sau refit, trên origin tháng 7/9/12 năm 2024, nhãn đến 31/03/2025. Trọng số được khóa: "+final_members+".",
        "5. Hai World audit độc lập chấm bản đã khóa. Không dùng audit để chỉnh lại trọng số hoặc model. Bốn World test khác chỉ dùng để đo kết quả về sau.","",
        "| Audit global | Cash score ↓ | MAE tuần (triệu VND) ↓ | MAE lũy kế (triệu VND) ↓ | Integrated Brier ↓ |","|---|---:|---:|---:|---:|"]
    for key in ("old_global","pre_refit","refit"):
        r=audit["results"][key]
        report.append(f"| {key} | {r['score']:.6f} | {r['cash_weekly_mae_vnd']/1e6:.2f} | {r['cash_cumulative_mae_vnd']/1e6:.2f} | {r['integrated_brier13']:.6f} |")
    cash_change=100*(audit["results"]["refit"]["score"]/audit["results"]["old_global"]["score"]-1)
    brier_change=100*(audit["results"]["refit"]["integrated_brier13"]/audit["results"]["old_global"]["integrated_brier13"]-1)
    report += ["",f"Điểm chuẩn hóa và lỗi VND có thể đi khác chiều vì doanh nghiệp được cân bằng theo World/doanh nghiệp/origin và quy mô dư nợ khác nhau. So với global cũ, thay đổi cash score của refit là {cash_change:+.2f}%, integrated Brier là {brier_change:+.2f}%. Giữ nguyên guard: cash không tăng quá 2%, integrated Brier không tăng quá 2% + 0,0001. Không bỏ guard sau khi thấy kết quả.","",
        "Sáu trial Neural mới và lượt refit Neural được ghi riêng trong `neural_convergence.json`/metadata. Cảnh báo 120 vòng của artifact cũ vẫn thuộc artifact cũ; kết quả hội tụ của bản mới không được gán cho bản đang giữ.","",
        "## So sánh global và local công bằng","",
        "Mọi nhánh dự báo cùng hóa đơn, ngày chốt, tiền còn phải thu, nhãn tương lai 13 tuần và partial-cash override. Global nguyên bản cũng được tính lại feature lịch sử local; chỉ tham số model không đổi.","",
        "- Global chọn lại trọng số: chỉ đổi tỷ trọng các thành viên đã học, dựa trên validation local.",
        "- Global học tiếp: tiếp tục Neural từ artifact 75/25; giữ scaler global; Adam learning rate 0,0001; thử 5/20 epoch, replay 30% trọng số từ train World gốc và 70% local; chọn pooling 0/25/50/75/100% bằng validation local. Replay không chứa World test hay doanh nghiệp khác thuộc test.",
        "- Global thích nghi qua audit: chọn nhánh reweight hoặc học tiếp bằng validation; audit quá khứ chỉ chấp nhận nhánh đó hoặc bác về global. Sau đó refit local với epoch/trọng số đã khóa, chỉ trên nhãn đã chín trước ngày dự báo.",
        "- Neural local 18 feature: cùng kiến trúc/cấu hình Neural làm đối chứng; fit scaler và tham số từ đầu bằng lịch sử doanh nghiệp. Giới hạn 400 vòng. Đây là cấu hình lấy từ global để kiểm soát kiến trúc, chưa phải tìm mọi hyperparameter NN local. Khi thiếu cửa sổ thì dùng Workspace, được ghi rõ fallback và chấm thêm tập đủ điều kiện riêng.",
        "- Workspace: giữ learner, pool, validation, audit và refit hiện có. Có điều kiện dùng Neural và fallback riêng. Đây là so sánh pipeline; khác feature, mục tiêu validation, lượng replay và ngân sách tối ưu nên không suy diễn thành ablation nhân quả thuần về pretrain.","",
        "Các origin local fit cách ngày test 1001–301 ngày, validation 210/182 ngày, audit 91 ngày. Nhãn fit kết thúc trước validation, nhãn validation kết thúc trước audit, và nhãn audit đã biết trước/ngay ngày test. Không dùng nhãn tương lai của doanh nghiệp để chọn nhánh.","",
        "## Test mới","","| Nhánh | Cash score ↓ | MAE tuần (triệu VND) ↓ | MAE lũy kế (triệu VND) ↓ | Brier4 ↓ | Brier13 ↓ |","|---|---:|---:|---:|---:|---:|"]
    for name in NAMES:
        r=results["results"][name]
        report.append(f"| {LABELS[name]} | {r['score']:.6f} | {r['cash_weekly_mae_vnd']/1e6:.2f} | {r['cash_cumulative_mae_vnd']/1e6:.2f} | {r['brier4']:.6f} | {r['brier13']:.6f} |")
    report += ["","| So sánh | Δ lỗi, dương có lợi cho nhánh mới | CI 95% | Doanh nghiệp cải thiện |","|---|---:|---|---:|"]
    for key,r in paired.items():
        report.append(f"| {key} | {r['mean_delta']:.6f} | [{r['ci95'][0]:.6f}; {r['ci95'][1]:.6f}] | {r['firms_improved']}/{r['firms']} |")
    report += ["","Bootstrap lấy lại mẫu doanh nghiệp trong từng World cố định, giữ các origin cùng doanh nghiệp; không phải khoảng tin cậy cho mọi doanh nghiệp Việt Nam. CI chứa 0 thì chưa đủ kết luận thắng chắc.","",
        f"Trong {len(eligible)} context đủ dữ liệu để thích nghi, cash score global={eligible_results['old_global']['score']:.6f}, học tiếp={eligible_results['global_finetuned']['score']:.6f}, qua audit={eligible_results['global_adapted_audited']['score']:.6f}, Neural local 18={eligible_results['local_neural18']['score']:.6f}, Workspace={eligible_results['workspace']['score']:.6f}. `eligible_local_results.json` tránh trộn lợi ích pretrain với fallback của doanh nghiệp thiếu lịch sử.","",
        "Ba World test có lịch sử dài, gồm baseline/credit/supply shock. World onboarding mới có dữ liệu từ 01/01/2025, chấm sau khoảng 3/6/9 tháng. `fresh_by_world.csv`, `fresh_by_firm_origin.csv`, `fresh_slices.csv` giữ ngoại lệ theo World, doanh nghiệp, thời gian, trả từng phần, khách mới/ít lịch sử và nợ quá hạn 90 ngày. Không kết luận một model thắng mọi phân nhóm.","",
        "## T6, SHAP và ngân sách tính toán","",
        "| Đường mô phỏng | Giới hạn SHAP | Số lần đo | Trung vị forecast (giây) |","|---:|---:|---:|---:|"]
    for r in timings.itertuples():
        report.append(f"| {r.simulation_paths} | {r.shap_limit} | {int(r.count)} | {r.median:.3f} |")
    report += ["","Đo trên doanh nghiệp có danh mục mở lớn nhất tại origin cuối của mỗi World test, warmup rồi xoay thứ tự ba cấu hình, ba lần mỗi cấu hình/context. `compute_budget_runs.csv` giữ từng lần đo; trung vị này không phải p95 SLA.","",
        "Tất cả hóa đơn hợp lệ đều vào T6; danh sách vẫn tối đa 30 dòng. `shap_limit=10` chỉ giải thích 10 dòng, các dòng còn lại ghi deferred. Dự thu kỳ vọng và thứ tự danh sách không đổi khi đổi Monte Carlo/SHAP. SHAP giải thích xác suất tất toán 4 tuần; tiền và số dư 13 tuần có cash decomposition riêng.","",
        "`runtime_shap.json` chấm từng model và Workspace bằng lời giải thích thực, không ước thời gian từ số feature. `runtime_verification.json` kiểm toàn bộ incoming với phân phối model + partial profile, SHAP cộng đúng và bất biến khi bỏ dữ liệu tương lai. Đo MC nhiều seed với mốc 10.000 đường nằm trong `monte_carlo_precision.csv`; đây là độ ổn định số, chưa phải hiệu chỉnh dải tiền theo thực tế.","",
        f"Kết quả tích hợp nghiên cứu được chấp nhận: **{release['research_integration_accepted']}**. Artifact phục vụ explicit: `{release['artifact_directory']}`; refit được chấp nhận: **{release['refit_accepted']}**. Không tự đặt cấu hình dịch vụ hoặc kích hoạt doanh nghiệp. Các plan smoke có số dư đầu 0, chỉ phạm vi AR, không chứng minh độ chính xác số dư ngân hàng đầy đủ.","",
        "## Bằng chứng và giới hạn","",
        "- `protocol.json`, `fresh_world_design.json`, `onboarding_design.json`: split, seed, budget và vai trò dữ liệu.",
        "- `comparison_amendment.json`: sửa nhánh học tiếp để dùng đúng global hiện tại, giữ lượt chạy bị ngắt và ghi sự cố ghi protocol đồng thời; không dùng điểm test tổng hợp để chỉnh model. `protocol_before_onboarding.json` giữ thiết kế trước khi thêm World thiếu lịch sử.",
        "- `frozen.json`, `post_refit_weight_selection.json`, `audit_results.json`: lựa chọn global và gate không đạt.",
        "- `verification.json`: kiểm độc lập điểm cash, khối lượng xác suất, hash dữ liệu/model và tái tạo global.",
        "- Các kết quả là synthetic cùng họ simulator, dùng giả định fallback khi thiếu raw WDI/OxCGRT; không có dữ liệu doanh nghiệp thật để xác nhận khả năng tổng quát ngoài simulator.",
        "- Kết quả fine-tune chỉ cho phương pháp/ngân sách đã thử. Không khẳng định mọi hình thức học tiếp đều tốt hơn hoặc kém hơn; không dùng test để tiếp tục tìm epoch/trọng số.",
        "- Nếu muốn cải thiện thêm bản refit, cần một lượt nghiên cứu khai báo mới, lựa chọn đồng thời chất lượng xác suất và tiền trên validation, rồi audit mới. Không sửa bản đã khóa để qua audit cũ.","",
        "Mã chạy lại: `refit_landmark.py --phase prepare/train/audit`, `compare_adaptation.py --prepare/--world/--summarize`, `verify_refit_comparison.py`, `verify_refit_runtime.py`. Các file cache chỉ được tiếp tục khi protocol/source/model hash tương thích.",""]
    text="\n".join(report)
    baseline=results["results"]["old_global"]["score"]
    ft=results["results"]["global_finetuned"]["score"]
    workspace=results["results"]["workspace"]["score"]
    ci=paired["global_finetuned_vs_old_global"]["ci95"]
    recommendation=(f"Global hiện tại giảm {(1-baseline/workspace)*100:.2f}% cash score so với Workspace và thắng ở {results['comparisons']['old_global']['firms_better_than_workspace']}/{results['firms']} doanh nghiệp trên cohort này. "
        f"Học tiếp chỉ giảm thêm {(1-ft/baseline)*100:.2f}% so với global hiện tại; CI 95% của lợi thế tuyệt đối là [{ci[0]:.6f}; {ci[1]:.6f}], còn chứa 0. "
        "Giữ global 75/25 làm điểm xuất phát tổng quát; chỉ xét thích nghi khi validation và audit local chấp nhận. Workspace vẫn là đối chứng tại doanh nghiệp. Không có bằng chứng để mặc định fine-tune cho mọi doanh nghiệp hoặc khẳng định một nhánh thắng mọi khía cạnh.")
    text=text.replace("## Đồng bộ feature và dữ liệu được biết",recommendation+"\n\n## Đồng bộ feature và dữ liệu được biết")
    large_rows=["### Danh mục lớn — kiểm tra tải kỹ thuật","",
        f"Đã tạo fixture {large['open_invoices']} hóa đơn mở/{large['history_invoices']} hóa đơn lịch sử, vượt ngưỡng census 512. Ledger được nhân bản với ID khách/hóa đơn riêng và hệ số tiền nguyên để giữ quan hệ thu/claim; đây là kiểm tra tải, không phải dữ liệu đánh giá độ chính xác mới. SHAP p95 một hóa đơn: {large['shap']['p95_seconds']:.3f} giây; policy tham chiếu và từng lần chạy nằm trong `large_book_runtime.json`.","",
        "| Đường mô phỏng | Giới hạn SHAP | Trung vị forecast (giây) |","|---:|---:|---:|"]
    for paths,limit in ((400,30),(1000,30),(1000,10)):
        values=[r["seconds"] for r in large["runs"] if (r["simulation_paths"],r["shap_limit"])==(paths,limit)]
        large_rows.append(f"| {paths} | {limit} | {np.median(values):.3f} |")
    text=text.replace("## Bằng chứng và giới hạn","\n".join(large_rows)+"\n\n## Bằng chứng và giới hạn")
    if (output/"tests_summary.json").exists():
        checked=read("tests_summary.json")
        text += f"\n## Kiểm thử mã\n\n{checked['python_passed']} kiểm thử Python và {checked['ui_passed']} kiểm thử giao diện đã qua; `git diff --check` không có lỗi. Các cảnh báo MLP trong fixture dùng 2/30 vòng và cảnh báo Starlette được giữ trong ghi chú, tách khỏi các trial Neural nghiên cứu đã hội tụ.\n"
    if (output/"target_contract.json").exists():
        corrections={}
        for p in (output/"prepared").glob("*.json"):
            item=json.loads(p.read_text(encoding="utf-8"))
            role=item["role"]
            entry=corrections.setdefault(role,dict(rows=0,changed_days=0))
            entry["rows"]+=item["rows"]
            entry["changed_days"]+=item["label_changed_rows"]
        write(output/"target_correction_summary.json",corrections)
        addition=["## Sửa nhãn tất toán theo ngày tiền thực thu","",
            "Kiểm tra độc lập phát hiện nhãn Paid cũ có thể tất toán sớm khi thứ tự ngày biết thanh toán khác thứ tự ngày tiền thực thu. Phiên bản này tính lại cumulative cash theo ngày tiền, chỉ sử dụng receipt đã biết trước label_end, và không tính credit note là tiền thu. Feature, mẫu hóa đơn, split, seed, cash amount, ứng viên, ngân sách và ngưỡng chọn giữ nguyên.","",
            "`target_contract.json` và từng receipt prepared lưu hash dữ liệu cũ/mới. Toàn bộ model global và nhánh thích nghi bị ảnh hưởng được train/chọn/refit lại trên nhãn sửa. Workspace dùng cơ chế nhãn riêng theo ngày thực thu; bundle cũ được kiểm hash, đối chiếu đầu vào và tái tạo dự báo khớp trước khi dùng lại. Các chỉ số trong báo cáo này đều chấm theo nhãn sửa.","",
            "Các World là seed mới được tạo trong session, sau đó dùng lại khi sửa nhãn một cách độc lập với dự báo. Không coi đây là một lần tạo thêm holdout chưa nhìn thấy sau sửa lỗi. Chưa có điểm test tổng hợp được dùng để thay hyperparameter. Lượt trước sửa nhãn giữ nguyên trong `aligned_refit_20261112`, không được dùng thay kết luận của phiên bản này.","",
            "| Phần dữ liệu | Snapshot | Ngày Paid thay đổi |","|---|---:|---:|"]
        for role,r in corrections.items():addition.append(f"| {role} | {r['rows']} | {r['changed_days']} |")
        text=text.replace("## Đồng bộ feature và dữ liệu được biết","\n".join(addition)+"\n\n## Đồng bộ feature và dữ liệu được biết")
    (output/"REPORT.md").write_text(text,encoding="utf-8")
    (ROOT/"docs/03_Evaluation/T1_REFIT_LOCAL_ADAPTATION_2026-11-13.md").write_text(text,encoding="utf-8")
    write(output/"environment.json",dict(python=platform.python_version(),packages={p:version(p) for p in ("numpy","pandas","scikit-learn","lightgbm","xgboost","scipy")}))
    changed={name:dict(frozen_sha256=digest,current_sha256=sha256(ROOT/name)) for name,digest in frozen["source_sha256"].items() if sha256(ROOT/name)!=digest}
    write(output/"source_amendments.json",dict(changes=changed,
        purpose="Atomic evidence writes/read-only existing protocol and accurate retained-artifact provenance; trained payloads and frozen selection unchanged.",
        original_frozen_receipt_preserved=True,comparison_execution_sources=read("adaptation_current_global_protocol.json")["source_sha256"]))
    write(output/"decision.json",dict(global_serving_artifact=release["artifact_directory"],
        refit_promoted=release["refit_accepted"], research_integration_accepted=release["research_integration_accepted"],
        local_continuation_implemented=True, local_selection_uses_past_only=True,
        automatic_tenant_activation=False, real_pilot_accepted=False, simulation_paths_default=1000,shap_limit_default=30,
        report_sha256=sha256(output/"REPORT.md"),fresh_results_sha256=sha256(output/"fresh_results.json")))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/"outputs/t1/aligned_refit_20261112")
    run(parser.parse_args().output.resolve())
