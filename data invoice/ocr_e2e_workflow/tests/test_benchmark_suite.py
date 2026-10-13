import json
from pathlib import Path

from PIL import Image

import src.runner as runner
from src.adapters.paddle_common import (
    paddle_classification_label,
    paddle_result_to_detections,
)
from src.adapter_worker import discard_recovered_native_failures, prepare_resume
from src.benchmark_suite import _run_is_complete, _safe_id
from src.reporting.suite_dashboard import render_bar_chart


def test_suite_id_is_safe_for_run_directories():
    assert _safe_id("dev 100/all") == "dev_100_all"


def test_completed_run_requires_both_prediction_files(tmp_path: Path):
    run_dir = tmp_path / "run"
    for relative, content in {
        "inputs/full_images.jsonl": "{}\n{}\n",
        "predictions/raw.jsonl": "{}\n{}\n",
        "inputs/recognition_crops.jsonl": "{}\n",
        "predictions/recognition_raw.jsonl": "{}\n",
    }.items():
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert _run_is_complete(run_dir)
    (run_dir / "predictions" / "recognition_raw.jsonl").write_text("", encoding="utf-8")
    assert not _run_is_complete(run_dir)


def test_native_crash_placeholder_is_not_a_completed_run(tmp_path: Path):
    run_dir = tmp_path / "run"
    for relative, content in {
        "inputs/full_images.jsonl": '{"image_id":"a.jpg"}\n',
        "predictions/raw.jsonl": json.dumps({
            "image_id": "a.jpg",
            "metadata": {"recovery_action": "sample_marked_failed"},
        }) + "\n",
        "inputs/recognition_crops.jsonl": '{"crop_id":"a_crop.jpg"}\n',
        "predictions/recognition_raw.jsonl": '{"image_id":"a_crop.jpg"}\n',
    }.items():
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert not _run_is_complete(run_dir)


def test_suite_chart_is_standalone_svg(tmp_path: Path):
    target = tmp_path / "chart.svg"
    rendered = render_bar_chart(
        [{"model_id": "ocr-a", "full_images": 100, "detection_f1_50": 0.75}],
        "detection_f1_50",
        "Detection F1",
        target,
        True,
    )
    assert rendered
    assert "<svg" in target.read_text(encoding="utf-8")


def test_resume_keeps_valid_predictions_and_drops_truncated_line(tmp_path: Path):
    output = tmp_path / "raw.jsonl"
    output.write_text('{"image_id":"a.jpg"}\n{"image_id":', encoding="utf-8")
    records = [{"image_id": "a.jpg"}, {"image_id": "b.jpg"}]

    remaining, completed = prepare_resume(output, records, True)

    assert completed == 1
    assert remaining == [{"image_id": "b.jpg"}]
    assert output.read_text(encoding="utf-8") == '{"image_id": "a.jpg"}\n'


def test_resume_retries_only_native_crash_recovery_rows(tmp_path: Path):
    output = tmp_path / "raw.jsonl"
    rows = [
        {"image_id": "good.jpg", "error": None},
        {
            "image_id": "native.jpg",
            "error": "native worker crash",
            "metadata": {"recovery_action": "sample_marked_failed"},
        },
        {"image_id": "python.jpg", "error": "ValueError"},
    ]
    output.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    assert discard_recovered_native_failures(output) == 1
    remaining, completed = prepare_resume(
        output, [{"image_id": row["image_id"]} for row in rows], True
    )
    assert completed == 2
    assert remaining == [{"image_id": "native.jpg"}]
    assert discard_recovered_native_failures(output) == 0


def test_native_crash_recovery_marks_sample_failed_and_continues(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (16, 12), "white").save(image_path)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"image_id": image_path.name, "image_path": str(image_path)}) + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"model_id": "fake", "output_mode": "boxes_and_text"}),
        encoding="utf-8",
    )
    output = tmp_path / "raw.jsonl"
    calls = {"count": 0}

    def fake_worker(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("native exit")

    monkeypatch.setattr(runner, "_run_worker", fake_worker)
    runner._run_worker_with_recovery(
        Path("python"),
        config,
        manifest,
        output,
        "run",
        tmp_path / "worker",
        "test",
        False,
        True,
        max_failed_samples=1,
    )

    prediction = json.loads(output.read_text(encoding="utf-8"))
    assert prediction["image_id"] == image_path.name
    assert "native worker crash" in prediction["error"]
    assert prediction["metadata"]["recovery_action"] == "sample_marked_failed"


def test_planned_worker_recycle_continues_until_manifest_is_complete(
    tmp_path: Path, monkeypatch
):
    records = [
        {"image_id": "a.jpg", "image_path": str(tmp_path / "a.jpg")},
        {"image_id": "b.jpg", "image_path": str(tmp_path / "b.jpg")},
    ]
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in records),
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"model_id": "fake"}), encoding="utf-8")
    output = tmp_path / "raw.jsonl"
    calls = {"count": 0}

    def fake_worker(*args, **kwargs):
        calls["count"] += 1
        remaining, _ = prepare_resume(output, records, True)
        with output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"image_id": remaining[0]["image_id"]}) + "\n")

    monkeypatch.setattr(runner, "_run_worker", fake_worker)
    runner._run_worker_with_recovery(
        Path("python"),
        config,
        manifest,
        output,
        "run",
        tmp_path / "worker",
        "test",
        False,
        False,
    )

    assert calls["count"] == 2
    assert [json.loads(line)["image_id"] for line in output.read_text().splitlines()] == [
        "a.jpg",
        "b.jpg",
    ]


def test_paddle_detection_helpers_support_standalone_model_results():
    class ArrayLike(list):
        def __bool__(self):
            raise ValueError("truth value of an array is ambiguous")

    results = [
        {
            "dt_polys": ArrayLike([
                [[1, 2], [5, 2], [5, 4], [1, 4]],
                [[8, 9], [12, 9], [12, 11], [8, 11]],
            ]),
            "dt_scores": ArrayLike([0.75, 0.65]),
        }
    ]
    detections = paddle_result_to_detections(results)
    assert len(detections) == 2
    assert detections[0]["confidence"] == 0.75
    assert detections[1]["confidence"] == 0.65
    assert paddle_classification_label(
        [{"label_names": ["90"], "scores": [0.99]}]
    ) == ("90", 0.99)
