from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.adapters.base import BaseAdapter
from src.utils import WORKFLOW_ROOT


class CommandAdapter(BaseAdapter):
    location_support = False

    def load_model(self) -> None:
        self.command = list(self.config.get("command") or [])
        if not self.command:
            raise ValueError(f"No command configured for {self.model_id}")

    def _load_output(self, output_dir: Path, stdout: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        json_files = sorted(output_dir.rglob("*.json"), key=lambda path: path.stat().st_mtime)
        if json_files:
            with json_files[-1].open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            blocks = value if isinstance(value, list) else [value]
            text = json.dumps(value, ensure_ascii=False)
            detections = []
            if isinstance(value, dict):
                text = str(value.get("markdown") or value.get("text") or text)
                detections = value.get("detections") or []
            return text, blocks, detections
        text_files = sorted(
            [*output_dir.rglob("*.md"), *output_dir.rglob("*.txt"), *output_dir.rglob("*.html")],
            key=lambda path: path.stat().st_mtime,
        )
        if text_files:
            return text_files[-1].read_text(encoding="utf-8"), [], []
        return stdout, [], []

    def infer(self, image_path: Path) -> dict[str, Any]:
        temporary_root = WORKFLOW_ROOT / "artifacts" / "cache" / "command_adapter"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temp:
            output_dir = Path(temp)
            command = [
                token.format(input=str(image_path), output_dir=str(output_dir), model_id=self.model_id)
                for token in self.command
            ]
            completed = subprocess.run(
                command,
                cwd=WORKFLOW_ROOT,
                capture_output=True,
                text=True,
                timeout=int(self.config.get("timeout_seconds", 600)),
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(f"command failed ({completed.returncode}): {completed.stderr[-2000:]}")
            text, blocks, detections = self._load_output(output_dir, completed.stdout)
            if detections:
                self.location_support = True
            return {
                "document_text_raw": text,
                "structured_blocks": blocks,
                "detections": detections,
                "metadata": {"command": command, "stderr": completed.stderr[-2000:]},
            }

