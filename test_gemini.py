"""Run this BEFORE the app:  python test_gemini.py
Checks (1) the .env key is found, (2) Gemini answers a text prompt, (3) Gemini can see an image.
The key is never printed."""
import io
import sys

from PIL import Image

from vision import DEFAULT_MODEL, friendly_error, generate, get_setting, key_status, get_api_key


def main():
    print("=== STEP 1: API key check ===")
    s = key_status()
    print("Looking for .env at :", s["env_path"])
    print("File exists         :", s["env_exists"])
    print("File encoding       :", s["encoding"])
    print("Variable names found:", s["names_in_file"])
    print("KEY FOUND           :", s["key_found"], f"(from {s['key_source']})" if s["key_found"] else "")
    print("KEY LENGTH          :", s["key_length"])
    if not s["key_found"]:
        print("\n[FAIL] PROBLEM:", s["problem"])
        print("Fix the .env file (see .env.example), save it, and run this test again.")
        sys.exit(1)
    print("[OK] Key loaded.\n")

    key, _ = get_api_key()
    model = get_setting("GEMINI_MODEL")[0] or DEFAULT_MODEL
    print(f"=== STEP 2: Text request to Gemini ({model}) ===")
    try:
        print("Reply:", generate(["Reply with exactly the word: ready"], key)[:80])
        print("[OK] Gemini connection works.\n")
    except Exception as exc:
        print("[FAIL]", friendly_error(exc, key))
        sys.exit(1)

    print("=== STEP 3: Image request to Gemini ===")
    try:
        from google.genai import types
        buf = io.BytesIO()
        Image.new("RGB", (128, 128), (220, 20, 20)).save(buf, format="PNG")
        part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
        print("Reply:", generate([part, "What single color fills this image? One word."], key)[:80])
        print("[OK] Image analysis works.\n")
    except Exception as exc:
        print("[FAIL]", friendly_error(exc, key))
        sys.exit(1)

    print("ALL CHECKS PASSED. Now run:  streamlit run app.py")


if __name__ == "__main__":
    main()
