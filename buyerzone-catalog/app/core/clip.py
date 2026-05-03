"""CLIP ViT-B/32 singleton — loads once, reused across the process."""

from __future__ import annotations

import io

from PIL import Image

_model = None
_preprocess = None
_tokenizer = None


def _load() -> None:
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return

    import open_clip  # type: ignore[import]

    _model, _, _preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32-quickgelu",
        pretrained="openai",
    )
    _tokenizer = open_clip.get_tokenizer("ViT-B-32")
    _model.eval()


def _get_model():
    _load()
    return _model, _preprocess, _tokenizer


def embed_image(image_bytes: bytes) -> list[float]:
    """Return L2-normalised 512-dim CLIP embedding for an image."""
    import torch

    model, preprocess, _ = _get_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = preprocess(image).unsqueeze(0)

    with torch.no_grad():
        features = model.encode_image(tensor)
        features /= features.norm(dim=-1, keepdim=True)

    return features.squeeze().tolist()


def embed_text(text: str) -> list[float]:
    """Return L2-normalised 512-dim CLIP embedding for a text query."""
    import torch

    model, _, tokenizer = _get_model()
    tokens = tokenizer([text])

    with torch.no_grad():
        features = model.encode_text(tokens)
        features /= features.norm(dim=-1, keepdim=True)

    return features.squeeze().tolist()
