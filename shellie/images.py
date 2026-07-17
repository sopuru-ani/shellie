"""Image classification + encoding for multimodal messages (stdlib only so no external image classification dependencies iykyk).

Vision models accept a small set of formats. This module detects the real type from magic bytes (not the file extension), so a mislabeled file is handled correctly and an
unsupported one is rejected with a clear message. No third-party dependencies.
"""

import base64
import urllib.request
from pathlib import Path

# Formats the vision model actually accepts.
SUPPORTED_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp")

# Extensions used ONLY as the auto-detect trigger in chat input. The real type is
# always confirmed by sniff_mime before anything is sent to the model.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# Cap downloaded/loaded images so a huge file can't blow up memory or the request.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


def sniff_mime(data: bytes) -> str | None:
    """Identify image type from magic bytes. Returns a MIME string or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def looks_like_image_ref(token: str) -> bool:
    """Cheap check for auto-detect: does this token look like an image path/URL?"""
    lowered = token.lower()
    base = lowered.split("?", 1)[0].split("#", 1)[0]
    return base.endswith(IMAGE_EXTENSIONS)


def _data_uri(mime: str, data: bytes) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def encode_local_image(path: str) -> tuple[str | None, str | None]:
    """Return (data_uri, error) for a local image file. Sniffs content, not extension."""
    p = Path(path).expanduser()
    if not p.is_file():
        return None, f"{path!r} not found."
    try:
        size = p.stat().st_size
    except OSError as exc:
        return None, f"could not stat {path!r}: {exc}"
    if size > _MAX_IMAGE_BYTES:
        return None, f"{path!r} is too large ({size} bytes; limit {_MAX_IMAGE_BYTES})."
    try:
        data = p.read_bytes()
    except OSError as exc:
        return None, f"could not read {path!r}: {exc}"
    mime = sniff_mime(data)
    if mime is None:
        return None, f"{path!r} is not a recognized image (PNG/JPEG/GIF/WEBP)."
    if mime not in SUPPORTED_MIMES:
        return None, f"{mime} is not supported by the model."
    return _data_uri(mime, data), None


def encode_url_image(url: str) -> tuple[str | None, str | None]:
    """Download, sniff, and base64-encode a remote image. Returns (data_uri, error)."""
    if not (url.startswith("http://") or url.startswith("https://")):
        return None, f"{url!r} is not an http(s) URL."
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read(_MAX_IMAGE_BYTES + 1)
    except Exception as exc:  # network errors vary widely; keep the REPL alive
        return None, f"could not download {url!r}: {exc}"
    if len(data) > _MAX_IMAGE_BYTES:
        return None, f"{url!r} is too large (limit {_MAX_IMAGE_BYTES} bytes)."
    mime = sniff_mime(data)
    if mime is None:
        return None, f"{url!r} did not return a recognized image (PNG/JPEG/GIF/WEBP)."
    if mime not in SUPPORTED_MIMES:
        return None, f"{mime} is not supported by the model."
    return _data_uri(mime, data), None


def encode_image_ref(ref: str) -> tuple[str | None, str | None]:
    """Encode either a local path or an http(s) URL. Returns (data_uri, error)."""
    if ref.startswith("http://") or ref.startswith("https://"):
        return encode_url_image(ref)
    return encode_local_image(ref)
