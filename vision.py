"""VisionMate helpers: API-key loading, image preparation, Gemini calls.

The API key is read from a .env file located NEXT TO THIS FILE (explicit path),
parsed by hand so it also works when Windows saved the file as UTF-16 or with a BOM.
The key itself is never printed or shown.
"""
import io
import os
import re
import time
from pathlib import Path

from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DEFAULT_MODEL = "gemini-3.1-flash-lite"
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
MAX_UPLOAD_MB = 10

PROMPT = """You are VisionMate, an assistant that describes images for blind and low-vision people.
Describe the image accurately in plain, simple English. Be specific and concrete.
Never identify real people by name from their faces; describe their visible appearance and actions instead.
If something is unclear, say so instead of guessing.

Reply using EXACTLY these headings, each on its own line starting with "## ", in this order:

## Summary
(2 to 3 short sentences describing the whole scene)

## Objects
(a list, one item per line starting with "- ", with position or color where useful)

## People
(a list starting with "- ", or write "No people visible")

## Surroundings
(setting, lighting, weather, background, mood)

## Visible Text
(transcribe readable text exactly, one item per line starting with "- ", or write "No readable text")

## Safety Notes
(hazards such as stairs, traffic, wet floors, sharp objects, or write "Nothing concerning noticed")

Do not add any other headings or commentary."""


# ---------------------------------------------------------------- .env handling
def _decode(raw: bytes):
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace"), "UTF-16 (PowerShell '>' default)"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "UTF-8 with BOM"
    if len(raw) > 1 and raw[1:2] == b"\x00":
        return raw.decode("utf-16-le", errors="replace"), "UTF-16 without BOM"
    return raw.decode("utf-8", errors="replace"), "UTF-8"


def read_env_file(path: Path = ENV_PATH):
    """Return (values dict, info dict). Values are never printed by this module."""
    info = {"path": str(path), "exists": path.is_file(), "encoding": None,
            "names": [], "wrong_files": []}
    values = {}
    if not info["exists"]:
        for name in (".env.txt", "env", "env.txt", ".env.example.txt"):
            if (path.parent / name).exists():
                info["wrong_files"].append(name)
        return values, info
    text, info["encoding"] = _decode(path.read_bytes())
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, _, val = line.partition("=")
        name, val = name.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1].strip()
        values[name] = val
        info["names"].append(name)
    return values, info


def _is_placeholder(value: str) -> bool:
    return value.upper().startswith(("PASTE", "YOUR_", "YOUR-", "YOUR "))


def get_setting(name: str):
    """Return (value, source). The .env file wins, then real environment variables."""
    values, _ = read_env_file()
    if values.get(name):
        return values[name], ".env file"
    if os.environ.get(name):
        return os.environ[name].strip(), "environment variable"
    return None, None


def get_api_key():
    """Return (key or None, source or None)."""
    for name in KEY_NAMES:
        value, source = get_setting(name)
        if value and not _is_placeholder(value):
            return value, source
    return None, None


def key_status() -> dict:
    """Safe-to-print diagnosis (never contains the key itself)."""
    values, info = read_env_file()
    key, source = get_api_key()
    problem = None
    if key is None:
        if not info["exists"]:
            if info["wrong_files"]:
                problem = (f"Found {info['wrong_files']} but no file named exactly '.env'. "
                           "Rename it to .env (Windows may be hiding the real extension).")
            else:
                problem = f"No .env file found at: {info['path']}"
        elif not any(n in values for n in KEY_NAMES):
            problem = ("The .env file exists, but it has no GEMINI_API_KEY line. "
                       f"Variable names found inside: {info['names'] or 'none'}")
        else:
            problem = ("GEMINI_API_KEY is empty or still the placeholder "
                       "(PASTE_YOUR_KEY_HERE). Paste your real key, then save the file.")
    return {"env_path": info["path"], "env_exists": info["exists"],
            "encoding": info["encoding"], "names_in_file": info["names"],
            "key_found": key is not None, "key_length": len(key) if key else 0,
            "key_source": source, "problem": problem}


# ---------------------------------------------------------------- images
def prepare_image(data: bytes):
    """Validate a JPG/PNG, fix rotation, shrink if huge. Returns (jpeg_bytes, 'image/jpeg')."""
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"This image is larger than {MAX_UPLOAD_MB} MB. Please choose a smaller one.")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except Exception:
        raise ValueError("This file could not be read as an image. Please upload a valid JPG, JPEG or PNG.")
    if fmt not in ("JPEG", "PNG"):
        raise ValueError(f"Unsupported image type ({fmt}). Please upload a JPG, JPEG or PNG.")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


# ---------------------------------------------------------------- Gemini
def generate(contents, api_key: str):
    """Call Gemini; retries briefly when the service is busy (503/500)."""
    from google import genai  # imported here so key checks work even before install
    client = genai.Client(api_key=api_key)
    model = get_setting("GEMINI_MODEL")[0] or DEFAULT_MODEL
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model, contents=contents)
            text = (response.text or "").strip()
            if not text:
                raise ValueError("The AI returned no text. The image may have been blocked by "
                                 "safety filters. Try a different image.")
            return text
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code in (500, 503) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def describe_image(image_bytes: bytes, mime_type: str, api_key: str) -> str:
    from google.genai import types
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    return generate([part, PROMPT], api_key)


def friendly_error(exc: Exception, api_key: str = "") -> str:
    """Turn an exception into a short, helpful message (key is never included)."""
    code = getattr(exc, "code", None)
    msg = str(exc)
    if api_key:
        msg = msg.replace(api_key, "[hidden]")
    low = msg.lower()
    if isinstance(exc, ValueError):
        return msg
    if "api key not valid" in low or "api_key_invalid" in low or "api key expired" in low:
        return "Google rejected the API key. Create a new key in Google AI Studio and update your .env file."
    if code == 403 or "permission_denied" in low:
        return "Access denied (403). Check that the key is correct and the Gemini API is allowed for it."
    if code == 404 or "not_found" in low:
        return ("The model name was not found. Add GEMINI_MODEL=<model name> to .env using a current "
                "model from https://ai.google.dev/gemini-api/docs/models")
    if code == 429 or "resource_exhausted" in low:
        return "Free-tier limit reached (429). Wait a minute and try again, or try again tomorrow."
    if code in (500, 503) or "unavailable" in low:
        return "Google's AI service is busy right now. Please try again in a moment."
    if code == 400:
        return f"Google could not process this request (400): {msg[:200]}"
    if any(w in low for w in ("connect", "timeout", "timed out", "getaddrinfo", "network")):
        return "Could not reach Google. Check your internet connection and try again."
    return f"Something went wrong ({type(exc).__name__}): {msg[:200]}"


# ---------------------------------------------------------------- result parsing
def parse_sections(text: str):
    """Split '## Heading' blocks into [(title, body)]."""
    sections, title, buf = [], None, []
    for line in text.splitlines():
        m = re.match(r"^\s{0,3}#{1,3}\s*(.+?)\s*#*\s*$", line)
        if m:
            if title is not None:
                sections.append((title, "\n".join(buf).strip()))
            title, buf = m.group(1).strip("*: "), []
        else:
            buf.append(line)
    if title is not None:
        sections.append((title, "\n".join(buf).strip()))
    return [(t, b) for t, b in sections if b]


def speech_text(sections, raw: str) -> str:
    """Plain text for text-to-speech (no bullets or markdown symbols)."""
    if not sections:
        return re.sub(r"[*_`#]", "", raw)
    parts = []
    for title, body in sections:
        lines = [re.sub(r"[*_`]", "", l).strip(" -•\t") for l in body.splitlines()]
        lines = [l.rstrip(".") for l in lines if l]
        parts.append(f"{title}. " + ". ".join(lines) + ".")
    return " ".join(parts)


def make_audio(text: str) -> bytes:
    """Free text-to-speech via gTTS (needs internet). Returns MP3 bytes."""
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text[:4500], lang="en", tld="co.in").write_to_fp(buf)
    return buf.getvalue()
