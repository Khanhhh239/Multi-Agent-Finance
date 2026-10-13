from __future__ import annotations

from typing import Any

from src.adapters.base import BaseAdapter


IMPLEMENTED_ADAPTERS = {
    "easyocr",
    "tesseract",
    "ppocrv6",
    "ppocrv6_vietocr",
    "paddleocr_vl",
    "surya",
    "glm_ocr",
    "hf_vlm",
    "hunyuan_ocr",
    "chandra",
    "dots_mocr",
    "command",
}


def create_adapter(config: dict[str, Any], run_id: str) -> BaseAdapter:
    adapter_name = config.get("adapter")
    if adapter_name == "easyocr":
        from src.adapters.easyocr_adapter import EasyOCRAdapter

        return EasyOCRAdapter(config, run_id)
    if adapter_name == "tesseract":
        from src.adapters.tesseract_adapter import TesseractAdapter

        return TesseractAdapter(config, run_id)
    if adapter_name == "ppocrv6":
        from src.adapters.ppocrv6_adapter import PPOCRv6Adapter

        return PPOCRv6Adapter(config, run_id)
    if adapter_name == "ppocrv6_vietocr":
        from src.adapters.vietocr_adapter import PPOCRV6VietOCRAdapter

        return PPOCRV6VietOCRAdapter(config, run_id)
    if adapter_name == "paddleocr_vl":
        from src.adapters.paddleocr_vl_adapter import PaddleOCRVLAdapter

        return PaddleOCRVLAdapter(config, run_id)
    if adapter_name == "surya":
        from src.adapters.surya_adapter import SuryaAdapter

        return SuryaAdapter(config, run_id)
    if adapter_name == "glm_ocr":
        from src.adapters.glm_ocr_adapter import GLMOCRAdapter

        return GLMOCRAdapter(config, run_id)
    if adapter_name == "hf_vlm":
        from src.adapters.hf_vlm_adapter import HFVLMAdapter

        return HFVLMAdapter(config, run_id)
    if adapter_name == "hunyuan_ocr":
        from src.adapters.hunyuan_ocr_adapter import HunyuanOCRAdapter

        return HunyuanOCRAdapter(config, run_id)
    if adapter_name == "chandra":
        from src.adapters.chandra_adapter import ChandraAdapter

        return ChandraAdapter(config, run_id)
    if adapter_name == "dots_mocr":
        from src.adapters.dots_mocr_adapter import DotsMOCRAdapter

        return DotsMOCRAdapter(config, run_id)
    if adapter_name == "command":
        from src.adapters.command_adapter import CommandAdapter

        return CommandAdapter(config, run_id)
    raise ValueError(f"Unknown adapter: {adapter_name}")
