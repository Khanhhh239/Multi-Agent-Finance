from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.adapters.base import BaseAdapter, flatten_document_text
from src.adapters.paddle_common import (
    paddle_classification_label,
    paddle_result_to_detections,
    polygon_to_original,
)
from src.utils import load_yaml, resolve_path


class PPOCRV6VietOCRAdapter(BaseAdapter):
    location_support = True

    def load_model(self) -> None:
        import torch
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        self.recognition_only = bool(self.config.get("recognition_only", False))
        self.location_support = not self.recognition_only
        self.detector = None
        self.orientation_classifier = None
        if not self.recognition_only:
            from paddleocr import DocImgOrientationClassification, TextDetection

            detector_config = self.config.get("detector", {})
            hybrid_threads = max(1, int(detector_config.get("hybrid_cpu_threads", 1)))
            common_kwargs: dict[str, Any] = {
                "enable_mkldnn": bool(detector_config.get("enable_mkldnn", False)),
                "cpu_threads": hybrid_threads,
            }
            device = self.config.get("device")
            if device and device != "auto":
                common_kwargs["device"] = device

            detection_kwargs = dict(common_kwargs)
            detection_kwargs["model_dir"] = str(
                resolve_path(detector_config["text_detection_model_dir"])
            )
            for option in (
                "limit_side_len", "limit_type", "thresh", "box_thresh",
                "unclip_ratio", "input_shape",
            ):
                if option in detector_config:
                    detection_kwargs[option] = detector_config[option]
            # VietOCR handles recognition; avoid loading Paddle's recognizer.
            self.detector = TextDetection(**detection_kwargs)

            if detector_config.get("use_doc_orientation_classify", False):
                orientation_dir = detector_config.get("doc_orientation_classify_model_dir")
                orientation_kwargs = dict(common_kwargs)
                if orientation_dir:
                    orientation_kwargs["model_dir"] = str(resolve_path(orientation_dir))
                self.orientation_classifier = DocImgOrientationClassification(
                    **orientation_kwargs
                )

        recognizer_config = self.config.get("recognizer", {})
        torch_threads = max(1, int(recognizer_config.get("cpu_threads", 1)))
        torch.set_num_threads(torch_threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # PyTorch permits setting inter-op threads only before parallel work starts.
            pass
        base_config_path = recognizer_config.get("base_config_path")
        architecture_config_path = recognizer_config.get("architecture_config_path")
        if base_config_path and architecture_config_path:
            merged_config = load_yaml(resolve_path(base_config_path))
            merged_config.update(load_yaml(resolve_path(architecture_config_path)))
            viet_config = Cfg(merged_config)
        else:
            viet_config = Cfg.load_config_from_name(
                recognizer_config.get("config_name", "vgg_transformer")
            )
        weights = recognizer_config.get("weights")
        if weights and resolve_path(weights).is_file():
            viet_config["weights"] = str(resolve_path(weights))
        viet_config["cnn"]["pretrained"] = False
        viet_config["device"] = "cuda:0" if self.config.get("device") in ("auto", "cuda") else "cpu"
        viet_config["predictor"]["beamsearch"] = bool(recognizer_config.get("beamsearch", False))
        if "image_max_width" in recognizer_config:
            width = int(recognizer_config["image_max_width"])
            if not 32 <= width <= 2048:
                raise ValueError('image_max_width must be 32..2048')
            viet_config["dataset"]["image_max_width"] = width
        self.recognizer = Predictor(viet_config)

    def _orientation(self, image: Image.Image) -> tuple[int, float | None]:
        if self.orientation_classifier is None:
            return 0, None
        results = self.orientation_classifier.predict(np.asarray(image))
        label, score = paddle_classification_label(results)
        try:
            return int(float(label)) % 360 if label is not None else 0, score
        except ValueError:
            return 0, score

    def infer(self, image_path: Path) -> dict[str, Any]:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        if self.recognition_only:
            segments = []
            try:
                from src.adapters.recognition_crops import line_segments
                options = self.config.get('recognizer', {})
                segments = line_segments(image, float(options.get('max_line_aspect', 14)),
                                         int(options.get('max_line_parts', 4))) if options.get('split_long_lines') else [(image.copy(), (0, image.width))]
                texts = [self.recognizer.predict(part).strip() for part, _ in segments]
                recognized = ' '.join(texts)
            finally:
                for part, _ in segments:
                    part.close()
                image.close()
            return {
                "document_text_raw": recognized,
                "metadata": {"recognizer_backend": "VietOCR", "recognition_only": True,
                             "segment_texts": texts, "x_spans": [list(span) for _, span in segments]},
            }
        angle, orientation_score = self._orientation(image)
        transpose = {
            90: Image.Transpose.ROTATE_90,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_270,
        }.get(angle)
        oriented_image = image.transpose(transpose) if transpose else image
        results = self.detector.predict(np.asarray(oriented_image))
        detections = paddle_result_to_detections(results)
        recognition_errors = 0
        split_detections = 0
        recognition_segments = []
        recognizer_config = self.config.get("recognizer", {})
        for detection in detections:
            oriented_polygon = detection["polygon"]
            xs = [point[0] for point in oriented_polygon]
            ys = [point[1] for point in oriented_polygon]
            box = (
                max(0, int(min(xs))),
                max(0, int(min(ys))),
                min(oriented_image.width, int(max(xs)) + 1),
                min(oriented_image.height, int(max(ys)) + 1),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                detection["text_raw"] = ""
                recognition_errors += 1
            else:
                crop = oriented_image.crop(box)
                try:
                    if recognizer_config.get("rectify_polygon", False):
                        from src.adapters.recognition_crops import rectified_crop
                        rectified = rectified_crop(oriented_image, oriented_polygon,
                                                  int(recognizer_config.get("crop_padding", 0)))
                        crop.close()
                        crop = rectified
                    if recognizer_config.get("split_long_lines", False):
                        from src.adapters.recognition_crops import line_segments
                        segments = line_segments(crop,
                            float(recognizer_config.get("max_line_aspect", 14)),
                            int(recognizer_config.get("max_line_parts", 4)))
                        try:
                            detection["text_raw"] = ' '.join(self.recognizer.predict(part).strip()
                                                              for part, _ in segments)
                            split_detections += int(len(segments) > 1)
                            if len(segments) > 1:
                                recognition_segments.append({
                                    'source_id': detection.get('source_id'),
                                    'x_spans': [list(span) for _, span in segments],
                                    'crop_size': list(crop.size),
                                    'oriented_bbox': list(box),
                                    'oriented_polygon': oriented_polygon,
                                    'rectified': bool(recognizer_config.get('rectify_polygon', False)),
                                    'padding': int(recognizer_config.get('crop_padding', 0)) if recognizer_config.get('rectify_polygon', False) else 0,
                                })
                        finally:
                            for part, _ in segments:
                                part.close()
                    else:
                        detection["text_raw"] = self.recognizer.predict(crop)
                except Exception:
                    detection["text_raw"] = ""
                    recognition_errors += 1
                finally:
                    crop.close()
            detection["polygon"] = polygon_to_original(
                oriented_polygon,
                image.size,
                angle,
            )
        if oriented_image is not image:
            oriented_image.close()
        image.close()
        return {
            "detections": detections,
            "document_text_raw": flatten_document_text(detections),
            "metadata": {
                "paddle_orientation_angle": angle,
                "paddle_orientation_score": orientation_score,
                "paddle_backend": "TextDetection",
                "recognizer_backend": "VietOCR",
                "recognition_errors": recognition_errors,
                "split_detections": split_detections,
                "recognition_segments": recognition_segments,
                "crop_policy": "experimental-line-split-v2" if recognizer_config.get("split_long_lines", False) else "axis-aligned-v1",
            },
        }
