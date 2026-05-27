"""CLIP ViT-B/32 singleton — loads once, reused across the process."""

from __future__ import annotations

import io

from PIL import Image

_model = None
_preprocess = None
_tokenizer = None
_device = None


def _get_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load() -> None:
    global _model, _preprocess, _tokenizer, _device
    if _model is not None:
        return

    import open_clip  # type: ignore[import]

    _device = _get_device()
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        "ViT-B-16-SigLIP",
        pretrained="webli",
        device=_device,
    )
    _tokenizer = open_clip.get_tokenizer("ViT-B-16-SigLIP")
    _model.eval()


def _get_model():
    _load()
    return _model, _preprocess, _tokenizer, _device


def embed_image(image_bytes: bytes) -> list[float]:
    """Return L2-normalised 512-dim CLIP embedding for an image."""
    import torch

    model, preprocess, _, device = _get_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = preprocess(image).unsqueeze(0).to(device)

    with torch.inference_mode():
        features = model.encode_image(tensor)
        features /= features.norm(dim=-1, keepdim=True)

    return features.squeeze().tolist()


def embed_text(text: str) -> list[float]:
    """Return L2-normalised 512-dim CLIP embedding for a text query."""
    import torch

    model, _, tokenizer, device = _get_model()
    tokens = tokenizer([text]).to(device)

    with torch.inference_mode():
        features = model.encode_text(tokens)
        features /= features.norm(dim=-1, keepdim=True)

    return features.squeeze().tolist()
