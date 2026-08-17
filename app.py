#!/usr/bin/env python3
"""
AI Vocals Studio - Streamlit Community Cloud version.

This free-hosted build keeps the public app lightweight. It provides the
permission-gated upload workflow and free text-to-speech generation. Heavy
voice-cloning engines should run from the Docker/local backend.
"""
import base64
import os
import tempfile
import time
from pathlib import Path

import streamlit as st
from gtts import gTTS


BASE = Path(os.environ.get("APP_DATA_DIR", tempfile.gettempdir())) / "ai-vocals-studio"
OUT = BASE / "outputs"
DATA = BASE / "dataset"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)


st.set_page_config(
    page_title="AI Vocals Studio",
    page_icon=":studio_microphone:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .stApp {
        background: linear-gradient(135deg, #101214 0%, #20252a 100%);
        color: white;
    }
    .stButton>button {
        background: linear-gradient(90deg, #00d084, #00a96b);
        color: #06110c;
        font-weight: 800;
        border: none;
        border-radius: 8px;
        min-height: 44px;
    }
    .main-header {
        font-size: 3rem;
        font-weight: 800;
        color: #00d084;
        text-align: center;
        margin-bottom: 0.5rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


def audio_player(audio_path: Path) -> None:
    try:
        audio_bytes = audio_path.read_bytes()
        mime = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        encoded = base64.b64encode(audio_bytes).decode()
        st.markdown(
            f"""
            <audio controls>
                <source src="data:{mime};base64,{encoded}" type="{mime}">
            </audio>
            """,
            unsafe_allow_html=True,
        )
    except OSError as exc:
        st.error(f"Could not play audio: {exc}")


def dataset_info() -> tuple[int, float]:
    files = []
    for ext in ("*.wav", "*.mp3", "*.m4a", "*.flac"):
        files.extend(DATA.glob(ext))
    size_mb = sum(path.stat().st_size for path in files) / (1024 * 1024)
    return len(files), size_mb


def main() -> None:
    st.markdown('<h1 class="main-header">AI Vocals Studio</h1>', unsafe_allow_html=True)
    st.markdown(
        "<h2 style='text-align:center;color:#00d084;'>Free Hosted Voice Studio</h2>",
        unsafe_allow_html=True,
    )
    st.warning(
        "Permission required: only upload or clone a voice you own, created yourself, "
        "or have explicit written permission/license to use. Do not clone artists, "
        "celebrities, public figures, private people, or copyrighted recordings "
        "without authorization."
    )

    file_count, size_mb = dataset_info()
    st.sidebar.markdown("## Dataset")
    st.sidebar.metric("Reference Audio Files", file_count)
    st.sidebar.metric("Dataset Size", f"{size_mb:.1f} MB")
    st.sidebar.markdown("## Engine")
    st.sidebar.info("Free cloud mode uses gTTS. Run the Docker backend for advanced cloning.")

    clone_tab, tts_tab, backend_tab = st.tabs(
        [":studio_microphone: Voice Workflow", ":speaking_head: Text-to-Speech", ":rocket: Advanced Backend"]
    )

    with clone_tab:
        st.markdown("### Authorized Reference Voice Workflow")
        st.info(
            "This free-hosted app accepts authorized reference uploads and permission confirmation. "
            "Realistic cloning runs from the heavier backend because free Streamlit hosting is too small "
            "for multi-GB voice models."
        )

        col1, col2 = st.columns([2, 1])
        with col1:
            ref_audio = st.file_uploader(
                "Upload authorized reference audio",
                type=["wav", "mp3", "m4a", "flac"],
            )
            ref_text = st.text_input(
                "Reference transcript",
                value="This is my authorized reference voice sample",
            )
            target_text = st.text_area(
                "Target text",
                value="This is a generated vocal take from AI Vocals Studio",
            )
            voice_label = st.text_input("Voice label", value="Authorized_Voice")

        with col2:
            has_permission = st.checkbox(
                "I own this voice or have explicit written permission/license to use it.",
                value=False,
            )
            if ref_audio is not None:
                suffix = Path(ref_audio.name).suffix or ".wav"
                saved = DATA / f"{voice_label.strip() or 'authorized_voice'}{suffix}"
                saved.write_bytes(ref_audio.getbuffer())
                st.success(f"Uploaded: {ref_audio.name}")
                audio_player(saved)

            if st.button("Generate Free Preview", type="primary", use_container_width=True):
                if not has_permission:
                    st.error("Confirm permission before generating audio.")
                elif not target_text.strip():
                    st.error("Enter target text first.")
                else:
                    output_path = OUT / f"preview_{int(time.time())}.mp3"
                    gTTS(text=target_text, lang="en").save(str(output_path))
                    st.success("Preview generated with the free cloud engine.")
                    audio_player(output_path)

    with tts_tab:
        st.markdown("### Free Text-to-Speech")
        text = st.text_area("Enter text", value="AI Vocals Studio is live on Streamlit Community Cloud.")
        if st.button("Generate Speech", type="primary"):
            if not text.strip():
                st.error("Enter text first.")
            else:
                output_path = OUT / f"speech_{int(time.time())}.mp3"
                gTTS(text=text, lang="en").save(str(output_path))
                st.success("Speech generated.")
                audio_player(output_path)

    with backend_tab:
        st.markdown("### Advanced Cloning Backend")
        st.write(
            "For realistic authorized voice cloning, run the Docker/local backend from the main repository. "
            "It includes the Qwen3-TTS integration, SoX, Streamlit health checks, and the permission-gated UI."
        )
        st.code("./launch_web.sh", language="bash")


if __name__ == "__main__":
    main()
