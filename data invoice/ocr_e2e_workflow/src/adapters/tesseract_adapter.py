from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PIL import Image

from src.adapters.base import BaseAdapter, flatten_document_text, rectangle_to_polygon
from src.utils import resolve_path


class TesseractAdapter(BaseAdapter):
    location_support = True

    def load_model(self) -> None:
        import pytesseract

        self.pytesseract = pytesseract
        if self.config.get("tesseract_cmd"):
            command = resolve_path(self.config["tesseract_cmd"])
            if not command.is_file():
                raise FileNotFoundError(f"Tesseract executable not found: {command}")
            pytesseract.pytesseract.tesseract_cmd = str(command)

        self.tesseract_options = f"--psm {int(self.config.get('psm', 6))}"
        if self.config.get("tessdata_dir"):
            tessdata_dir = resolve_path(self.config["tessdata_dir"])
            if not tessdata_dir.is_dir():
                raise FileNotFoundError(f"Tesseract language directory not found: {tessdata_dir}")
            # Tesseract 5.0 on Windows treats quotes in --tessdata-dir as part
            # of the path. The worker is an isolated subprocess, so setting
            # TESSDATA_PREFIX here is both robust for paths with spaces and
            # contained to this model run.
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)

    def _orient_image(self, image: Image.Image) -> tuple[Image.Image, int, float]:
        if not self.config.get("auto_orient", False):
            return image, 0, 0.0
        min_area = int(self.config.get("auto_orient_min_area", 250_000))
        if image.width * image.height < min_area:
            return image, 0, 0.0
        try:
            osd = self.pytesseract.image_to_osd(
                image,
                output_type=self.pytesseract.Output.DICT,
            )
            rotation = int(osd.get("rotate", 0)) % 360
            confidence = float(osd.get("orientation_conf", 0.0))
        except self.pytesseract.TesseractError:
            return image, 0, 0.0
        if confidence < float(self.config.get("orientation_min_confidence", 2.0)):
            return image, 0, confidence
        transpose = {
            90: Image.Transpose.ROTATE_270,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_90,
        }.get(rotation)
        return (image.transpose(transpose) if transpose else image), rotation, confidence

    @staticmethod
    def _to_original_polygon(
        polygon: list[list[float]], rotation: int, width: int, height: int
    ) -> list[list[float]]:
        if rotation == 90:
            return [[y, height - x] for x, y in polygon]
        if rotation == 180:
            return [[width - x, height - y] for x, y in polygon]
        if rotation == 270:
            return [[width - y, x] for x, y in polygon]
        return polygon

    def infer(self, image_path: Path) -> dict[str, Any]:
        source_image = Image.open(image_path)
        source_width, source_height = source_image.size
        image, rotation, orientation_confidence = self._orient_image(source_image)
        output = self.pytesseract.image_to_data(
            image,
            lang=self.config.get("language", "vie+eng"),
            config=self.tesseract_options,
            output_type=self.pytesseract.Output.DICT,
        )
        lines: dict[tuple[int, int, int, int], dict[str, Any]] = {}
        for index, text in enumerate(output["text"]):
            text = str(text).strip()
            confidence = float(output["conf"][index])
            if not text or confidence < 0:
                continue
            key = tuple(
                int(output[name][index])
                for name in ("page_num", "block_num", "par_num", "line_num")
            )
            left = float(output["left"][index])
            top = float(output["top"][index])
            right = left + float(output["width"][index])
            bottom = top + float(output["height"][index])
            line = lines.setdefault(
                key,
                {
                    "words": [],
                    "confidences": [],
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "source_ids": [],
                },
            )
            line["words"].append(text)
            line["confidences"].append(confidence)
            line["left"] = min(line["left"], left)
            line["top"] = min(line["top"], top)
            line["right"] = max(line["right"], right)
            line["bottom"] = max(line["bottom"], bottom)
            line["source_ids"].append(str(index))

        detections = []
        for line in lines.values():
            confidence = sum(line["confidences"]) / len(line["confidences"])
            polygon = rectangle_to_polygon(
                line["left"],
                line["top"],
                line["right"] - line["left"],
                line["bottom"] - line["top"],
            )
            detections.append(
                {
                    "polygon": self._to_original_polygon(
                        polygon, rotation, source_width, source_height
                    ),
                    "text_raw": " ".join(line["words"]),
                    "confidence": min(1.0, max(0.0, confidence / 100)),
                    "source_id": ",".join(line["source_ids"]),
                }
            )
        return {
            "detections": detections,
            "document_text_raw": flatten_document_text(detections),
            "metadata": {
                "orientation_rotation": rotation,
                "orientation_confidence": orientation_confidence,
            },
        }
