"""Model loading and local inference. No remote inference clients."""
from pathlib import Path

TEXT = "HuggingFaceTB/SmolLM2-135M-Instruct"
VISION = "HuggingFaceTB/SmolVLM-256M-Instruct"
TEXT_EXT = {".txt", ".md", ".csv", ".json"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def read_turn(prompt, files, vision):
    parts = []
    if len(files) > 3:
        raise ValueError("Attach at most three files per message.")
    for filename in files:
        path = Path(filename)
        ext = path.suffix.lower()
        if ext in TEXT_EXT:
            if path.stat().st_size > 32_768:
                raise ValueError("Text attachments must be 32 KiB or smaller.")
            body = path.read_text(encoding="utf-8-sig")
            parts.append({"type": "text", "text": f"File: {path.name}\n{body}"})
        elif vision and ext in IMAGE_EXT:
            from PIL import Image
            if path.stat().st_size > 8 * 1024**2:
                raise ValueError("Images must be 8 MiB or smaller.")
            with Image.open(path) as img:
                if img.width * img.height > 16_000_000:
                    raise ValueError("Choose an image under 16 megapixels.")
                parts.append({"type": "image", "image": img.convert("RGB")})
        else:
            raise ValueError(f"This model does not accept {ext or 'this file type'}.")
    if prompt.strip():
        parts.append({"type": "text", "text": prompt.strip()})
    if not parts:
        raise ValueError("Enter a message or attach a file.")
    return {"role": "user", "content": parts}


class Engine:
    def __init__(self, repo, cached):
        import torch
        from huggingface_hub.utils import validate_repo_id
        from transformers import (AutoConfig, AutoModelForCausalLM,
                                  AutoModelForImageTextToText, AutoProcessor, AutoTokenizer)
        validate_repo_id(repo)
        if Path(repo).exists():
            raise ValueError("Enter a Hugging Face repository ID.")
        options = dict(local_files_only=cached, trust_remote_code=False)
        cfg = AutoConfig.from_pretrained(repo, **options)
        self.vision = cfg.model_type in {"smolvlm", "idefics3"}
        processor = AutoProcessor if self.vision else AutoTokenizer
        self.processor = processor.from_pretrained(repo, **options)
        if not getattr(self.processor, "chat_template", None):
            raise ValueError("Choose an instruction model with a built-in chat template.")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        loader = AutoModelForImageTextToText if self.vision else AutoModelForCausalLM
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = loader.from_pretrained(repo, use_safetensors=True, torch_dtype=dtype,
                                            **options).to(self.device).eval()
        text_cfg = getattr(cfg, "text_config", cfg)
        self.limit = getattr(text_cfg, "max_position_embeddings", 4096)

    def reply(self, messages):
        import torch
        if self.vision:
            inputs = self.processor.apply_chat_template(messages, tokenize=True,
                add_generation_prompt=True, return_dict=True, return_tensors="pt")
        else:
            plain = [{"role": m["role"], "content": "\n".join(p["text"] for p in m["content"])}
                     for m in messages]
            inputs = self.processor.apply_chat_template(plain, tokenize=True,
                add_generation_prompt=True, return_dict=True, return_tensors="pt")
        inputs = inputs.to(self.device)
        length = inputs["input_ids"].shape[1]
        budget = min(192, self.limit - length)
        if budget < 1:
            raise ValueError("The conversation exceeds this model's context. Clear chat or shorten the file.")
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=budget, do_sample=False)
        return self.processor.batch_decode(output[:, length:], skip_special_tokens=True)[0].strip()
