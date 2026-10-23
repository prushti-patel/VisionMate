
import streamlit as st

st.markdown("""
    <style>
        [data-testid="stToolbar"] {
            visibility: hidden;
            height: 0%;
            position: fixed;
        }
        #MainMenu {
            visibility: hidden;
        }
        footer {
            visibility: hidden;
        }
    </style>
""", unsafe_allow_html=True)
"""VisionMate - AI-powered accessibility assistant (Streamlit + Gemini)."""
import hashlib

import streamlit as st

from vision import (describe_image, friendly_error, get_api_key, key_status, make_audio,
                    parse_sections, prepare_image, speech_text)

st.set_page_config(page_title="VisionMate", page_icon="👁️", layout="wide",
                   initial_sidebar_state="collapsed")

# ------------------------------------------------------------------ styling
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&display=swap');
:root { --navy:#0B2545; --blue:#134074; --sky:#8DA9C4; --mist:#EAF2FB; --line:#D5E3F3; --ink:#14213D; }
.stApp, .stMarkdown, .stButton button, label, p, li { font-family: 'Manrope','Segoe UI',system-ui,sans-serif; }
[data-testid="stMainBlockContainer"], .block-container { max-width: 1040px; padding-top: 2rem; }
footer { visibility: hidden; }
.stButton > button, .stDownloadButton > button { border-radius: 14px; font-weight: 700; padding: .7rem 1.2rem; }
.stButton > button:focus-visible { outline: 3px solid var(--sky); outline-offset: 2px; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; border-color: var(--line); box-shadow: 0 6px 20px rgba(11,37,69,.07); }

.vm-hero { position:relative; overflow:hidden; background:var(--navy); color:#fff; border-radius:26px;
  padding:3rem 2.5rem 3rem; box-shadow:0 16px 40px rgba(11,37,69,.25); }
.vm-hero .vm-rings { position:absolute; right:-90px; top:-90px; width:420px; height:420px; pointer-events:none; }
.vm-hero > *:not(.vm-rings) { position:relative; }
.vm-hero h1 { color:#fff; margin:1rem 0 .2rem; padding:0; font-weight:800; font-size:clamp(2.3rem,5vw,3.6rem); letter-spacing:-.02em; }
.vm-hero .vm-tag { color:var(--sky); font-size:1.35rem; font-weight:600; margin:0 0 1rem; }
.vm-hero .vm-intro { color:#E6EEF8; font-size:1.08rem; line-height:1.65; max-width:560px; margin:0; }

.vm-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:1.1rem; margin:1.6rem 0 1.2rem; }
.vm-card { background:#fff; border:1px solid var(--line); border-radius:20px; padding:1.4rem 1.3rem; box-shadow:0 6px 20px rgba(11,37,69,.08); }
.vm-card .vm-ico { width:46px; height:46px; border-radius:14px; background:var(--mist); display:flex; align-items:center; justify-content:center; font-size:1.4rem; margin-bottom:.8rem; }
.vm-card h3 { color:var(--navy); font-size:1.08rem; font-weight:800; margin:0 0 .35rem; padding:0; }
.vm-card p { color:#33415C; font-size:.95rem; line-height:1.55; margin:0; }

.vm-head h2 { color:var(--navy); font-weight:800; margin:0; padding:0; font-size:1.9rem; }
.vm-head p { color:#33415C; margin:.3rem 0 1.2rem; font-size:1.02rem; }
.vm-summary { background:var(--mist); border-left:6px solid var(--navy); border-radius:16px; padding:1.1rem 1.3rem; color:var(--ink); font-size:1.12rem; line-height:1.7; }
</style>
"""

LOGO = """<svg width="84" height="84" viewBox="0 0 96 96" role="img" aria-label="VisionMate eye logo">
<circle cx="48" cy="48" r="46" fill="#EAF2FB"/>
<path d="M10 48C20 30 34 22 48 22s28 8 38 26c-10 18-24 26-38 26S20 66 10 48Z" fill="#fff" stroke="#0B2545" stroke-width="4" stroke-linejoin="round"/>
<circle cx="48" cy="48" r="14" fill="#0B2545"/><circle cx="48" cy="48" r="6" fill="#8DA9C4"/><circle cx="53" cy="43" r="3" fill="#fff"/></svg>"""

RINGS = """<svg class="vm-rings" viewBox="0 0 420 420" aria-hidden="true" fill="none" stroke="#8DA9C4">
<circle cx="210" cy="210" r="200" stroke-opacity=".18" stroke-width="2"/><circle cx="210" cy="210" r="150" stroke-opacity=".22" stroke-width="2"/>
<circle cx="210" cy="210" r="100" stroke-opacity=".28" stroke-width="2"/><circle cx="210" cy="210" r="50" stroke-opacity=".35" stroke-width="2"/></svg>"""

FEATURES = [
    ("🖼️", "Plain-language descriptions", "Upload a photo and get a clear explanation of what is happening in it."),
    ("🔎", "Objects, people and text", "Important items, who is there, and any readable text are listed separately."),
    ("🔊", "Listen instead of read", "Play the description aloud with one button."),
    ("♿", "Built to be easy to use", "High contrast, large buttons and only one task per page."),
]

SECTION_ICONS = {"summary": "📝", "objects": "📦", "people": "🧍", "surroundings": "🌆",
                 "visible text": "🔤", "safety": "⚠️"}

# ------------------------------------------------------------------ state
DEFAULTS = {"page": "home", "image_bytes": None, "image_name": None, "image_hash": None,
            "result_text": None, "audio": None, "error": None, "uploader_key": 0}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def go(page):
    st.session_state.page = page


def clear_image():
    st.session_state.update(image_bytes=None, image_name=None, image_hash=None,
                            result_text=None, audio=None, error=None,
                            uploader_key=st.session_state.uploader_key + 1)


def analyze_another():
    clear_image()
    st.session_state.page = "analyze"


def page_head(title, subtitle):
    st.html(f'<div class="vm-head"><h2>{title}</h2><p>{subtitle}</p></div>')


# ------------------------------------------------------------------ page 1
def home_page():
    cards = "".join(f'<div class="vm-card"><div class="vm-ico">{i}</div><h3>{t}</h3><p>{d}</p></div>'
                    for i, t, d in FEATURES)
    st.html(f"""<section class="vm-hero">{RINGS}<div>{LOGO}</div>
<h1>VisionMate</h1><p class="vm-tag">See the world through words.</p>
<p class="vm-intro">Upload any photo and VisionMate explains it in simple language: the scene, the objects,
the people and any text, ready to be read aloud.</p></section>
<div class="vm-grid">{cards}</div>""")
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.button("Start Exploring", type="primary", width="stretch", on_click=go, args=("analyze",))


# ------------------------------------------------------------------ page 2
def show_key_help():
    s = key_status()
    with st.expander("How to fix the API key problem", expanded=True):
        st.write(s["problem"] or "Key looks fine.")
        st.code(f"Expected file: {s['env_path']}\nExpected line: GEMINI_API_KEY=your_real_key", language="text")
        st.write("Then run `python test_gemini.py` in PowerShell to confirm, and restart the app.")


def analyze_page():
    page_head("Analyze an image", "Upload a JPG, JPEG or PNG photo, check the preview, then press Analyze Image.")
    uploaded = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"],
                                key=f"uploader_{st.session_state.uploader_key}")
    if uploaded is not None:
        raw = uploaded.getvalue()
        digest = hashlib.md5(raw).hexdigest()
        if digest != st.session_state.image_hash:
            try:
                data, _mime = prepare_image(raw)
                st.session_state.update(image_bytes=data, image_name=uploaded.name, image_hash=digest,
                                        result_text=None, audio=None, error=None)
            except ValueError as exc:
                st.session_state.update(image_bytes=None, image_name=None, image_hash=None,
                                        result_text=None, audio=None, error=str(exc))

    if st.session_state.image_bytes:
        with st.container(border=True):
            st.image(st.session_state.image_bytes, caption=st.session_state.image_name, width="stretch")
            st.button("Remove image", on_click=clear_image)

    if st.session_state.error:
        st.error(st.session_state.error)

    c1, c2 = st.columns([2, 1])
    with c1:
        analyze_clicked = st.button("Analyze Image", type="primary", width="stretch",
                                    disabled=not st.session_state.image_bytes)
    with c2:
        st.button("Back to Home", width="stretch", on_click=go, args=("home",))

    if st.session_state.result_text:
        st.button("View previous result", on_click=go, args=("results",))

    if analyze_clicked:
        key, _src = get_api_key()
        if not key:
            st.session_state.error = "Gemini API key not found. Follow the steps below."
            st.error(st.session_state.error)
            show_key_help()
            return
        try:
            with st.spinner("Analyzing your image. This usually takes a few seconds..."):
                text = describe_image(st.session_state.image_bytes, "image/jpeg", key)
            st.session_state.update(result_text=text, audio=None, error=None, page="results")
            st.rerun()
        except Exception as exc:  # show a friendly message, never the key
            st.session_state.error = friendly_error(exc, key)
            st.error(st.session_state.error)


# ------------------------------------------------------------------ page 3
def results_page():
    page_head("AI results", "Here is what VisionMate found in your image.")
    text = st.session_state.result_text
    if not text:
        st.info("There is no result yet. Upload and analyze an image first.")
        st.button("Go to Image Analysis", type="primary", on_click=go, args=("analyze",))
        st.button("Back to Home", on_click=go, args=("home",))
        return

    sections = parse_sections(text)
    left, right = st.columns([1, 2], gap="large")
    with left:
        if st.session_state.image_bytes:
            with st.container(border=True):
                st.image(st.session_state.image_bytes, width="stretch")
    with right:
        if not sections:
            with st.container(border=True):
                st.markdown(text)
        for title, body in sections:
            icon = next((v for k, v in SECTION_ICONS.items() if title.lower().startswith(k)), "•")
            with st.container(border=True):
                st.markdown(f"#### {icon} {title}")
                if title.lower().startswith("summary"):
                    st.html(f'<div class="vm-summary">{body}</div>')
                else:
                    st.markdown(body)

    st.divider()
    if st.button("🔊 Read Aloud", type="primary"):
        try:
            with st.spinner("Preparing audio..."):
                st.session_state.audio = make_audio(speech_text(sections, text))
        except Exception:
            st.session_state.audio = None
            st.warning("Audio could not be created. It needs an internet connection. "
                       "The written description above is still available.")
    if st.session_state.audio:
        st.audio(st.session_state.audio, format="audio/mp3")

    b1, b2 = st.columns(2)
    with b1:
        st.button("Analyze Another Image", width="stretch", on_click=analyze_another)
    with b2:
        st.button("Back to Home", width="stretch", on_click=go, args=("home",))


# ------------------------------------------------------------------ router
st.html(CSS)
{"home": home_page, "analyze": analyze_page, "results": results_page}.get(
    st.session_state.page, home_page)()
