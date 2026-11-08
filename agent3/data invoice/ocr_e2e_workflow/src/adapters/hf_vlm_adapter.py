from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from src.adapters.base import BaseAdapter


class HFVLMAdapter(BaseAdapter):
    location_support = False

    def load_model(self) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        model_name = self.config["model_name"]
        revision = self.config.get("revision")
        kwargs = {"trust_remote_code": True}
        if revision:
            kwargs["revision"] = revision
        self.processor = AutoProcessor.from_pretrained(model_name, **kwargs)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_name,
            torch_dtype="auto",
            device_map="auto",
            **kwargs,
        )

    def infer(self, image_path: Path) -> dict[str, Any]:
        image = Image.open(image_path).convert("RGB")
        prompt = self.config.get(
            "prompt",
            "Transcribe every visible character faithfully in natural reading order. Do not explain or invent text.",
        )
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        rendered = self.processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        inputs = self.processor(text=[rendered], images=[image], return_tensors="pt")
        device = next(self.model.parameters()).device
        inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
        generated = self.model.generate(
            **inputs,
            max_new_tokens=int(self.config.get("max_new_tokens", 4096)),
            do_sample=False,
        )
        input_length = inputs["input_ids"].shape[1] if "input_ids" in inputs else 0
        text = self.processor.batch_decode(generated[:, input_length:], skip_special_tokens=True)[0]
        return {"document_text_raw": text, "metadata": {"output_tokens": int(generated.shape[1] - input_length)}}

