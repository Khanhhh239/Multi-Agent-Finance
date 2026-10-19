from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from src.adapters.base import BaseAdapter, flatten_document_text
from src.adapters.paddle_common import paddle_result_orientation, paddle_result_to_detections,_as_dict
from src.utils import resolve_path


class PPOCRv6Adapter(BaseAdapter):
    location_support = True

    def load_model(self) -> None:
        self.recognition_only=bool(self.config.get('recognition_only',False))
        if self.recognition_only:
            from paddleocr import TextRecognition
            self.location_support=False
            self.recognizer=TextRecognition(model_dir=str(resolve_path(self.config['text_recognition_model_dir'])),
                device=self.config.get('device','cpu'),enable_mkldnn=False,cpu_threads=1)
            return
        from paddleocr import PaddleOCR

        kwargs: dict[str, Any] = {}
        detection_dir = self.config.get("text_detection_model_dir")
        recognition_dir = self.config.get("text_recognition_model_dir")
        if detection_dir or recognition_dir:
            if detection_dir:
                kwargs["text_detection_model_dir"] = str(resolve_path(detection_dir))
            if recognition_dir:
                kwargs["text_recognition_model_dir"] = str(resolve_path(recognition_dir))
        else:
            kwargs["ocr_version"] = self.config.get("ocr_version", "PP-OCRv6")
            kwargs["lang"] = self.config.get("lang", "vi")

        for option in (
            "doc_orientation_classify_model_dir",
            "use_doc_orientation_classify",
            "use_doc_unwarping",
            "use_textline_orientation",
            "enable_mkldnn",
            "cpu_threads",
        ):
            if option in self.config:
                value = self.config[option]
                if option.endswith("_dir"):
                    value = str(resolve_path(value))
                kwargs[option] = value
        device = self.config.get("device")
        if device and device != "auto":
            kwargs["device"] = device
        self.ocr = PaddleOCR(**kwargs)

    def infer(self, image_path: Path) -> dict[str, Any]:
        if self.recognition_only:
            values=[];scores=[]
            for result in self.recognizer.predict(str(image_path)):
                value=_as_dict(result);value=value.get('res',value)
                values.append(str(value.get('rec_text','')))
                scores.append(value.get('rec_score'))
            return {'document_text_raw':' '.join(values),'metadata':{'recognition_only':True,
                'recognizer_backend':'PP-OCRv6_medium_rec','recognition_scores':scores,
                'confidence_semantics':'RECOGNITION_HEURISTIC_NOT_CALIBRATED'}}
        if hasattr(self.ocr, "predict"):
            results = list(self.ocr.predict(str(image_path)))
        else:
            results = self.ocr.ocr(str(image_path))
        with Image.open(image_path) as image:
            source_size = image.size
        detections = paddle_result_to_detections(results, source_size=source_size)
        return {
            "detections": detections,
            "document_text_raw": flatten_document_text(detections),
            "metadata": {"paddle_orientation_angle": paddle_result_orientation(results)},
        }
