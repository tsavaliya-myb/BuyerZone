"""ViT-B-16-SigLIP singleton — loads once per process, compiled for faster CPU inference."""

from __future__ import annotations

import io
import threading

from PIL import Image

_model = None
_preprocess = None
_tokenizer = None
_device = None
_load_lock = threading.Lock()


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
        return  # fast path — no lock needed

    with _load_lock:
        if _model is not None:
            return  # another thread loaded it while we waited

        import torch

        # Prevent CPU thrashing across multiple gunicorn/arq workers
        torch.set_num_threads(1)

        import open_clip  # type: ignore[import]

        _device = _get_device()
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            "ViT-B-16-SigLIP",
            pretrained="webli",
            device=_device,
        )
        _tokenizer = open_clip.get_tokenizer("ViT-B-16-SigLIP")
        _model.eval()

        # torch.compile() generates optimised native code on first call.
        # Subsequent calls (all real inference) are 20–40% faster on CPU.
        # First call after startup will be slow (compilation) — that's expected.
        # g++ is required by the inductor backend — installed in Dockerfile runtime stage.
        # suppress_errors=True is a safety net: if compile fails for any reason,
        # it silently falls back to eager mode instead of crashing embed calls.
        if _device.type == "cpu":
            try:
                import torch._dynamo as _dynamo
                _dynamo.config.suppress_errors = True
                _model.encode_image = torch.compile(
                    _model.encode_image,
                    mode="reduce-overhead",   # best for repeated same-shape inputs
                    fullgraph=False,          # allow partial graph capture (safer)
                )
                _model.encode_text = torch.compile(
                    _model.encode_text,
                    mode="reduce-overhead",
                    fullgraph=False,
                )
            except Exception:
                pass  # compile is best-effort; fall back to eager if it fails


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
