from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from src.adapters.base import BaseAdapter


class DotsMOCRAdapter(BaseAdapter):
    """dots.mocr Hugging Face adapter following the upstream inference path."""

    location_support = False

    def load_model(self) -> None:
        import torch
        from dots_mocr.utils import dict_promptmode_to_prompt
        from transformers import AutoModelForCausalLM, AutoProcessor

        self.torch = torch
        self.prompt = self.config.get("prompt") or dict_promptmode_to_prompt[
            self.config.get("prompt_mode", "prompt_layout_all_en")
        ]
        model_name = self.config["model_name"]
        self.processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
        )

    def infer(self, image_path: Path) -> dict[str, Any]:
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
                    {"type": "text", "text": self.prompt},
                ],
            }
        ]
        rendered = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[rendered],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        device = next(self.model.parameters()).device
        inputs = inputs.to(device)
        generated = self.model.generate(
            **inputs, max_new_tokens=int(self.config.get("max_new_tokens", 24000))
        )
        trimmed = [output[len(source) :] for source, output in zip(inputs.input_ids, generated)]
        text = self.processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        return {"document_text_raw": text}
