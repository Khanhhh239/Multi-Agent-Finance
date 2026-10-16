import json
from pathlib import Path
from types import SimpleNamespace
import unicodedata

import pytest

from agent4.agent.retriever import Candidate, MetricRetriever, normalize
from agent4.engine.metrics import REGISTRY
from eval.bench_retriever import DEFAULT_DATA, benchmark


@pytest.fixture(scope="module")
def retriever():
    return MetricRetriever()


@pytest.mark.parametrize("question,gold", [
    ("Doanh thu thuần tháng này là bao nhiêu?", "net_revenue"),
    ("Doanh thu thuần quý này so với quý trước tăng hay giảm bao nhiêu phần trăm?", "net_revenue"),
    ("Giá vốn hàng bán theo từng tháng trong 6 tháng gần nhất?", "cogs"),
    ("Biên lợi nhuận gộp tháng này là bao nhiêu?", "gross_margin_pct"),
    ("Lợi nhuận gộp theo từng sản phẩm/dịch vụ là bao nhiêu?", "gross_profit"),
    ("Chi phí bán hàng và quản lý doanh nghiệp tháng này gồm những khoản nào?", "expense_by_category"),
    ("Lợi nhuận thuần hoạt động kinh doanh lũy kế từ đầu năm?", "operating_profit"),
    ("Lợi nhuận sau thuế tháng này và so với cùng kỳ năm trước?", "net_profit"),
    ("Tiền mặt và tiền gửi ngân hàng hiện còn bao nhiêu?", "cash_and_equivalents"),
    ("Dòng tiền thuần trong tháng này là bao nhiêu?", "net_cash_flow"),
])
def test_m1_metric_in_candidates(retriever, question, gold):
    assert gold in {c.metric for c in retriever.topk(question)}


def test_vietnamese_normalization_and_determinism(retriever):
    question = "Doanh thu thuần quý trước?"
    expected = retriever.topk(question)
    assert expected == retriever.topk(unicodedata.normalize("NFD", question))
    assert expected == retriever.topk("DOANH THU THUAN QUY TRUOC")
    assert normalize("Đầu kỳ") == "dau ky"


def test_k_bounds_and_unknown_input(retriever):
    assert retriever.topk("doanh thu", k=0) == []
    assert retriever.topk("doanh thu", k=-1) == []
    assert len(retriever.topk("doanh thu", k=1)) == 1
    assert len(retriever.topk("doanh thu", k=999)) <= len(REGISTRY)
    assert retriever.topk("") == []
    assert retriever.topk("1234 !@#$") == []
    assert retriever.topk("zyxwvu") == []


def test_hint_capabilities_boost_without_admitting_metrics(retriever):
    plain = {c.metric: c.score for c in retriever.topk("chi phí", k=66)}
    tax = {c.metric: c.score for c in retriever.topk("chi phí", k=66, hints={"view_hint": "tax"})}
    grouped = {c.metric: c.score for c in retriever.topk("chi phí", k=66, hints=SimpleNamespace(group_by="cost_category"))}
    assert set(plain) == set(tax) == set(grouped)
    for key in plain:
        assert tax[key] == pytest.approx(plain[key] + (2 if "tax" in REGISTRY[key].views else 0))
        assert grouped[key] == pytest.approx(plain[key] + (3 if "cost_category" in REGISTRY[key].group_bys else 0))


def test_ambiguity_is_conservative(retriever):
    assert retriever.ambiguous([])
    assert retriever.ambiguous([Candidate("a", 1)])
    assert retriever.ambiguous([Candidate("a", 10), Candidate("b", 9.5)])
    assert not retriever.ambiguous([Candidate("a", 30), Candidate("b", 10)])


def test_index_uses_only_registry_metadata(retriever):
    assert set(retriever._ids) == set(REGISTRY)
    assert not hasattr(retriever, "engine")
    for metric, phrases in retriever._phrases.items():
        assert phrases == tuple(normalize(p) for p in (REGISTRY[metric].label, *REGISTRY[metric].synonyms))


def test_handwritten_smoke_coverage_and_recall(retriever):
    rows = [json.loads(line) for line in DEFAULT_DATA.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 100
    assert len({r["question"] for r in rows}) == 100
    assert {r["gold"] for r in rows} == set(REGISTRY)
    hits = sum(r["gold"] in {c.metric for c in retriever.topk(r["question"], hints=r.get("hints"))} for r in rows)
    assert hits / len(rows) >= .99


def test_benchmark_reports_measurements_and_limits(tmp_path):
    source = tmp_path / "mini.jsonl"
    source.write_text(json.dumps({"question": "doanh thu thuan", "gold": "net_revenue"}), encoding="utf-8")
    result = benchmark(source, repeats=1)
    assert result["recall_at_k"] == 1
    assert result["latency_ms"]["max"] > 0
    assert result["initialization_ms"] > 0
    assert result["notice"] == "công thức chưa được kế toán duyệt (G0.7 mở)"
    assert "not held out" in result["dataset_role"]
