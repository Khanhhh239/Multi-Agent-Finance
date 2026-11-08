from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.utils import (
    WORKFLOW_ROOT,
    environment_dir_from_python,
    load_yaml,
    resolve_python_executable,
)


REQUIREMENTS = {
    "easyocr": "requirements/easyocr.txt",
    "tesseract": "requirements/tesseract.txt",
    "ppocrv6_medium": "requirements/ppocrv6.txt",
    "ppocrv6_vietocr": "requirements/vietocr.txt",
    "paddleocr_vl_1_6": "requirements/paddleocr_vl.txt",
    "surya_ocr_2": "requirements/surya.txt",
    "glm_ocr": "requirements/glm_ocr.txt",
    "hunyuan_ocr_1_5": "requirements/hunyuan_ocr.txt",
    "chandra_ocr_2": "requirements/chandra.txt",
    "dots_mocr": "requirements/dots_mocr.txt",
}


def setup_model_environment(model_id: str) -> Path:
    if model_id not in REQUIREMENTS:
        raise KeyError(f"No requirements mapping for {model_id}")
    config = load_yaml(WORKFLOW_ROOT / "configs" / "models" / f"{model_id}.yaml")
    minimum_python = config.get("minimum_python")
    if minimum_python:
        required = tuple(int(part) for part in str(minimum_python).split(".")[:2])
        if sys.version_info[:2] < required:
            raise RuntimeError(
                f"{model_id} requires Python >= {minimum_python}; current interpreter is "
                f"{sys.version_info.major}.{sys.version_info.minor}"
            )
    environment_dir = environment_dir_from_python(config["python"])
    target_python = resolve_python_executable(config["python"])
    if not target_python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(environment_dir)], check=True, cwd=WORKFLOW_ROOT)
        target_python = resolve_python_executable(config["python"])
    subprocess.run(
        [str(target_python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        cwd=WORKFLOW_ROOT,
    )
    subprocess.run(
        [str(target_python), "-m", "pip", "install", "-r", str(resolve_path(REQUIREMENTS[model_id]))],
        check=True,
        cwd=WORKFLOW_ROOT,
    )
    return target_python
