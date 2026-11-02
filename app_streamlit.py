#!/usr/bin/env python3
"""
AI Vocals Studio - Streamlit Web Version
Professional consent-based voice cloning interface for web deployment.
"""
import streamlit as st
import os
import tempfile
import threading
import time
from pathlib import Path
from gtts import gTTS
import base64
import json

# Try to import voice cloning engines
try:
    from qwen3_tts_engine import Qwen3TTSEngine
    HAS_QWEN_ENGINE = True
except ImportError:
    HAS_QWEN_ENGINE = False

# Configuration
BASE = os.environ.get("APP_DATA_DIR", os.path.expanduser("~/ai-vocals-studio"))
OUT = os.environ.get("OUTPUT_DIR", os.path.join(BASE, "outputs"))
DATA = os.environ.get("DATASET_DIR", os.path.join(BASE, "dataset"))
MODELS = os.environ.get("MODEL_CACHE_DIR", os.path.join(BASE, "models"))
VOICES = os.path.join(MODELS, "voices")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)
os.makedirs(MODELS, exist_ok=True)
os.makedirs(VOICES, exist_ok=True)

# Page config
st.set_page_config(
    page_title="AI Vocals Studio - Voice Cloning",
    page_icon=":studio_microphone:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for dark theme
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #1a1a1a 0%, #2b2b2b 100%);
        color: white;
    }
    .stButton>button {
        background: linear-gradient(90deg, #00ff88, #00cc6a);
        color: black;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #00cc6a, #00ff88);
        transform: translateY(-2px);
    }
    .stTextInput>div>div>input {
        background: #3a3a3a;
        color: white;
        border: 1px solid #00ff88;
    }
    .stTextArea>div>div>textarea {
        background: #3a3a3a;
        color: white;
        border: 1px solid #00ff88;
    }
    .stSelectbox>div>div>select {
        background: #3a3a3a;
        color: white;
    }
    .stProgress .progress-bar {
        background: linear-gradient(90deg, #00ff88, #00cc6a);
    }
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00ff88, #00cc6a);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

def init_session_state():
    """Initialize session state variables"""
    if 'qwen_engine' not in st.session_state:
        st.session_state.qwen_engine = Qwen3TTSEngine() if HAS_QWEN_ENGINE else None
    if 'has_qwen_runtime' not in st.session_state:
        st.session_state.has_qwen_runtime = bool(
            st.session_state.qwen_engine and st.session_state.qwen_engine.can_clone()
        )
    if 'cloning_progress' not in st.session_state:
        st.session_state.cloning_progress = 0
    if 'cloning_status' not in st.session_state:
        st.session_state.cloning_status = "Ready"
    if 'saved_voices' not in st.session_state:
        st.session_state.saved_voices = []
    refresh_saved_voices()

def refresh_saved_voices():
    """Refresh the list of persisted cloned voices from models/voices/."""
    try:
        from qwen3_tts_engine import list_saved_voices
        st.session_state.saved_voices = list_saved_voices(VOICES)
    except Exception:
        st.session_state.saved_voices = []

def load_voice_dataset():
    """Load and display local reference dataset information."""
    dataset_info = {
        'total_files': 0,
        'total_size_mb': 0,
        'files': []
    }

    if os.path.exists(DATA):
        for ext in ['*.wav', '*.mp3', '*.m4a', '*.flac']:
            files = list(Path(DATA).glob(ext))
            dataset_info['files'].extend(files)

        dataset_info['total_files'] = len(dataset_info['files'])
        dataset_info['total_size_mb'] = sum(f.stat().st_size for f in dataset_info['files']) / (1024*1024)

    return dataset_info

def clone_voice_worker(ref_audio_path, ref_text, target_text, speaker_name, persist=True, has_permission=False):
    """Background worker for voice cloning (x-vector-only: transcript optional)"""
    try:
        if not st.session_state.qwen_engine:
            st.session_state.qwen_engine = Qwen3TTSEngine()
        if not st.session_state.qwen_engine.can_clone():
            st.session_state.cloning_status = "Qwen3-TTS engine unavailable"
            st.session_state.cloning_progress = 0
            return

        # Update progress
        st.session_state.cloning_status = "Loading model..."
        st.session_state.cloning_progress = 20

        # Load model
        def progress_cb(msg, progress):
            st.session_state.cloning_status = msg
            st.session_state.cloning_progress = progress

        if not st.session_state.qwen_engine.load_model(progress_cb=progress_cb):
            st.session_state.cloning_status = "Failed to load model"
            return

        st.session_state.cloning_status = "Cloning voice..."
        st.session_state.cloning_progress = 50

        # Clone voice (no transcript required — speaker-embedding clone)
        output_path = st.session_state.qwen_engine.clone_voice(
            ref_audio=ref_audio_path,
            ref_text=(ref_text or None),
            target_text=target_text,
            speaker_name=speaker_name,
            progress_cb=progress_cb,
            has_permission=has_permission,
        )

        if output_path:
            st.session_state.cloning_status = f"Success! Saved to: {output_path}"
            st.session_state.cloning_progress = 100
            st.session_state.last_output = output_path
            if persist:
                try:
                    st.session_state.qwen_engine.save_clone(
                        speaker_name, ref_audio_path,
                        description="Cloned from uploaded reference audio",
                        has_permission=has_permission)
                    refresh_saved_voices()
                except Exception:
                    pass
        else:
            st.session_state.cloning_status = "Cloning failed"
            st.session_state.cloning_progress = 0

    except Exception as e:
        st.session_state.cloning_status = f"Error: {str(e)}"
        st.session_state.cloning_progress = 0

def audio_player(audio_path):
    """Create audio player for file"""
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        base64_audio = base64.b64encode(audio_bytes).decode()
        audio_html = f"""
        <audio controls>
            <source src="data:audio/wav;base64,{base64_audio}" type="audio/wav">
        </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not play audio: {e}")


def _save_upload(upload, folder: Path) -> str:
    """Persist a Streamlit upload and return its local path."""
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.name).suffix or ".wav"
    safe_stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(upload.name).stem)
    path = folder / f"{safe_stem}_{int(time.time() * 1000)}{suffix}"
    path.write_bytes(upload.getbuffer())
    return str(path)


def _ui_progress(status_box, progress_bar):
    def progress_cb(message, pct):
        progress_bar.progress(max(0, min(100, int(pct))))
        status_box.info(message)
    return progress_cb


def run_voiceover_builder(
    *,
    voice_files,
    target_audio,
    voice_label: str,
    voice_source_type: str,
    mode: str,
    script_text: str,
    has_permission: bool,
    voice_gain_db: float,
    bed_gain_db: float,
    mood: str,
    status_box,
    progress_bar,
) -> dict:
    """Run the easy UI workflow using the same backend as the CLI."""
    if not has_permission:
        raise ValueError("Confirm permission before generating audio.")
    if not voice_files:
        raise ValueError("Upload at least one voice sample.")
    if not target_audio:
        raise ValueError("Upload the song, beat, or target audio.")
    if mode == "Voice-over on beat/song" and not script_text.strip():
        raise ValueError("Enter the voice-over text.")

    from clone_any_voice import (
        convert_target_audio,
        mix_voiceover_over_bed,
        synthesize_voiceover,
    )
    from voice_cloner import build_voice_profile_from_sources

    run_id = int(time.time())
    upload_dir = Path(DATA) / "ui_runs" / str(run_id)
    output_dir = Path(OUT) / "voiceover_builder" / str(run_id)
    voice_paths = [_save_upload(upload, upload_dir / "voices") for upload in voice_files]
    target_path = _save_upload(target_audio, upload_dir / "target")
    label = voice_label.strip() or f"Authorized_Voice_{run_id}"

    progress = _ui_progress(status_box, progress_bar)
    profile = build_voice_profile_from_sources(
        name=label,
        source_paths=voice_paths,
        source_type=voice_source_type,
        description="Built from Voice-Over Builder uploads",
        voices_dir=VOICES,
        progress_cb=progress,
        has_permission=True,
    )
    if not profile:
        raise RuntimeError("Could not build the cloned voice profile.")

    output_dir.mkdir(parents=True, exist_ok=True)
    if mode == "Voice-over on beat/song":
        voiceover_path = synthesize_voiceover(profile, script_text, output_dir, mood=mood)
        mixed_path = output_dir / f"{profile.get('name', 'voice')}_mixed_voiceover.wav"
        final_path = mix_voiceover_over_bed(
            voiceover_path,
            target_path,
            mixed_path,
            voice_gain_db=voice_gain_db,
            bed_gain_db=bed_gain_db,
        )
        report_path = output_dir / "quality_report.json"
        status = "voiceover_mix"
    else:
        target_type = "song" if mode == "Replace vocals in song" else "clip"
        final_path = convert_target_audio(
            profile,
            target_path,
            target_type,
            output_dir,
            vocals_gain_db=voice_gain_db,
        )
        report_path = output_dir / "quality_report.json"
        status = "voice_conversion"

    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
        except Exception:
            report = {}
    progress_bar.progress(100)
    status_box.success("Generation complete.")
    return {
        "status": status,
        "profile": profile,
        "output": str(final_path),
        "report": report,
        "report_path": str(report_path) if report_path.exists() else "",
        "output_dir": str(output_dir),
    }

def main():
    init_session_state()

    # Header
    st.markdown('<h1 class="main-header">:studio_microphone: AI Vocals Studio</h1>', unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; color: #00ff88;'>Consent-Based Voice Cloning & Generation</h2>", unsafe_allow_html=True)
    st.warning(
        "Permission required: only upload or clone a voice you own, created yourself, "
        "or have explicit written permission/license to use. Do not clone artists, "
        "celebrities, public figures, private people, or copyrighted recordings "
        "without authorization."
    )

    # Sidebar
    st.sidebar.markdown("## :gear: Settings")
    with st.sidebar.expander("Cloud engines"):
        eleven_key = st.text_input(
            "ElevenLabs API key",
            type="password",
            help="Optional. Enables the ElevenLabs backend for authorized voice-over jobs.",
        )
        if st.button("Save ElevenLabs key", use_container_width=True):
            if not eleven_key.strip():
                st.warning("Enter an API key first.")
            else:
                cfg_path = Path(".cloud_config")
                lines = []
                if cfg_path.exists():
                    lines = [
                        line for line in cfg_path.read_text(errors="ignore").splitlines()
                        if not line.startswith("ELEVENLABS_API_KEY=")
                    ]
                lines.append(f"ELEVENLABS_API_KEY={eleven_key.strip()}")
                cfg_path.write_text("\n".join(lines) + "\n")
                os.environ["ELEVENLABS_API_KEY"] = eleven_key.strip()
                st.success("ElevenLabs key saved for this deployment/workspace.")

    # Engine selection
    available_engines = ["gTTS (Free)"]
    if st.session_state.has_qwen_runtime:
        available_engines.append("Qwen3-TTS (Advanced)")

    selected_engine = st.sidebar.selectbox("Voice Engine", available_engines)

    # Dataset info
    st.sidebar.markdown("## :file_folder: Dataset")
    dataset_info = load_voice_dataset()
    st.sidebar.metric("Reference Audio Files", dataset_info['total_files'])
    st.sidebar.metric("Dataset Size", f"{dataset_info['total_size_mb']:.1f} MB")
    with st.sidebar.expander("Engine status"):
        try:
            from engine_planner import get_engine_status

            for engine in get_engine_status():
                label = "ready" if engine["available"] else "unavailable"
                st.caption(f"{engine['name']}: {label} - {engine['note']}")
        except Exception as e:
            st.caption(f"Engine status unavailable: {e}")

    # Main tabs
    builder_tab, tab1, tab2, tab3, tab4 = st.tabs([
        ":studio_microphone: Voice-Over Builder",
        ":musical_note: Song to Voice",
        ":speaking_head: Text-to-Speech",
        ":robot_face: Models",
        ":bar_chart: Analytics",
    ])

    with builder_tab:
        st.markdown("### Voice-Over Builder")
        st.markdown("Upload the voice you want, upload the song or beat, enter the line, then generate the take.")

        left, right = st.columns([2, 1])
        with left:
            voice_files = st.file_uploader(
                "Voice to clone",
                type=["wav", "mp3", "m4a", "flac", "ogg", "aac", "aiff"],
                accept_multiple_files=True,
                key="builder_voice_files",
            )
            if voice_files:
                st.caption(f"{len(voice_files)} voice sample(s) selected")
                st.audio(voice_files[0])

            target_audio = st.file_uploader(
                "Song, beat, or audio that needs the voice",
                type=["wav", "mp3", "m4a", "flac", "ogg", "aac", "aiff"],
                key="builder_target_audio",
            )
            if target_audio:
                st.audio(target_audio)

            script_text = st.text_area(
                "Voice-over text",
                height=140,
                placeholder="Type what the cloned voice should say over the song or beat...",
                key="builder_script_text",
            )

        with right:
            mode = st.selectbox(
                "Output mode",
                ["Voice-over on beat/song", "Replace vocals in song", "Convert spoken/rap clip"],
                key="builder_mode",
            )
            voice_source_type = st.selectbox(
                "Voice sample type",
                ["speech", "song", "text"],
                index=0,
                key="builder_voice_source_type",
            )
            voice_label = st.text_input("Voice label", value="Authorized_Voice", key="builder_voice_label")
            mood = st.selectbox("Delivery", ["default", "aggressive", "storytelling", "emotional"], key="builder_mood")
            voice_gain_db = st.slider("Voice gain", -12.0, 12.0, 0.0, 0.5, key="builder_voice_gain")
            bed_gain_db = st.slider("Beat/song bed gain", -18.0, 3.0, -3.0, 0.5, key="builder_bed_gain")
            has_permission = st.checkbox(
                "I own this voice or have explicit written permission/license to use it.",
                value=False,
                key="builder_permission",
            )
            generate = st.button("Generate Voice-Over", type="primary", use_container_width=True)

        progress_bar = st.progress(0)
        status_box = st.empty()

        if generate:
            try:
                with st.spinner("Building voice and generating audio..."):
                    result = run_voiceover_builder(
                        voice_files=voice_files,
                        target_audio=target_audio,
                        voice_label=voice_label,
                        voice_source_type=voice_source_type,
                        mode=mode,
                        script_text=script_text,
                        has_permission=has_permission,
                        voice_gain_db=voice_gain_db,
                        bed_gain_db=bed_gain_db,
                        mood=mood,
                        status_box=status_box,
                        progress_bar=progress_bar,
                    )
                st.session_state.builder_last_result = result
                refresh_saved_voices()
            except Exception as e:
                status_box.error(str(e))

        result = st.session_state.get("builder_last_result")
        if result:
            st.markdown("#### Output")
            audio_player(result["output"])
            with open(result["output"], "rb") as f:
                st.download_button(
                    "Download WAV",
                    data=f.read(),
                    file_name=Path(result["output"]).name,
                    mime="audio/wav",
                    use_container_width=True,
                )
            report = result.get("report") or {}
            score = report.get("estimated_accuracy", {})
            plan = report.get("plan", {})
            if plan:
                p1, p2, p3 = st.columns(3)
                p1.metric("Selected Engine", plan.get("engine", "unknown"))
                p2.metric("Plan Confidence", f"{plan.get('confidence', 0)}%")
                p3.metric("Reference Confidence", f"{plan.get('reference_confidence', 0)}%")
            if score:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Accuracy", f"{score.get('score', 0)}%")
                c2.metric("Pitch", f"{score.get('pitch', 0)}%")
                c3.metric("Timbre", f"{score.get('timbre', 0)}%")
                c4.metric("Confidence", f"{score.get('confidence', 0)}%")
                st.caption("Accuracy is an engineering estimate from pitch, timbre envelope, loudness, and reference duration.")
            ref_quality = report.get("reference_quality") or {}
            if ref_quality:
                q1, q2, q3 = st.columns(3)
                q1.metric("Reference Quality", f"{round(float(ref_quality.get('overall', 0)) * 100, 1)}%")
                q2.metric("Voiced Content", f"{round(float(ref_quality.get('voiced_fraction', 0)) * 100, 1)}%")
                q3.metric("Noise/SNR", f"{ref_quality.get('snr_db', 0)} dB")
                st.caption("For better cloning, upload clean single-speaker voice with low background music/noise and no clipping.")
            if result.get("report_path"):
                st.code(result["report_path"])

    with tab1:
        st.markdown("### :musical_note: Put Song Lyrics Into an Authorized Voice")
        st.markdown("Upload the song, upload the authorized voice, then generate the lyrics with that cloned voice.")
        st.info(
            "By continuing, you confirm the reference audio and target voice are authorized "
            "for this use, including any rights-holder approval that may be required."
        )

        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("#### Step 1: Upload the Song")
            song_audio = st.file_uploader("Choose the song whose lyrics you want to use", type=['wav', 'mp3', 'm4a', 'flac'], key="song_audio")
            if song_audio:
                st.success(f"Song uploaded: {song_audio.name}")
                st.audio(song_audio)
            with st.expander("Which song upload is best?"):
                st.write("WAV or FLAC gives the cleanest source audio. MP3 is smaller and uploads faster but may lose detail. M4A is supported but can be slower to process.")

            st.markdown("#### Step 2: Upload the Voice To Clone")
            ref_audio = st.file_uploader("Choose an authorized voice reference", type=['wav', 'mp3', 'm4a', 'flac'], key="voice_audio")

            if ref_audio:
                # Save uploaded file temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                    tmp_file.write(ref_audio.read())
                    tmp_audio_path = tmp_file.name

                st.success(f"Uploaded: {ref_audio.name}")
                audio_player(tmp_audio_path)

            with st.expander("Which voice upload is best?"):
                st.write("A clean WAV or FLAC recording with one speaker and little background music gives the most faithful result. MP3 works, but heavy compression, effects, or multiple voices reduce quality.")

            st.markdown("#### Step 3: Reference transcript (optional)")
            no_transcript = st.checkbox(
                "I don't have a transcript — clone from the voice alone (recommended)",
                value=True,
                help="Qwen3-TTS clones from the speaker embedding only, so a transcript "
                     "is not required. Providing one can tighten delivery.")
            ref_text = ""
            if not no_transcript:
                ref_text = st.text_input("Reference text", value="This is my reference voice sample",
                                         help="Enter exactly what's said in the reference audio")

            st.markdown("#### Step 4: Paste the Song Lyrics")
            target_text = st.text_area("Lyrics for the cloned voice", placeholder="Paste the lyrics from the uploaded song here...", height=150,
                                     help="Paste lyrics you have the right to use. The authorized cloned voice performs this text.")
            speaker_name = st.text_input("Voice label", value="Authorized_Voice",
                                       help="Use a project-safe label for the cloned voice (saved under models/voices/)")

        with col2:
            st.markdown("#### Step 5: Create Vocal Take")
            has_permission = st.checkbox(
                "I own this voice or have explicit written permission/license to clone it.",
                value=False
            )

            if st.button(":studio_microphone: Create With Cloned Voice", type="primary", use_container_width=True):
                if not st.session_state.has_qwen_runtime:
                    st.error("Qwen3-TTS not installed! Install with: pip install qwen-tts")
                elif not song_audio:
                    st.error("Please upload the song first")
                elif not ref_audio:
                    st.error("Please upload a reference audio file")
                elif not target_text:
                    st.error("Please enter the target text")
                elif not has_permission:
                    st.error("Confirm that you own the voice or have explicit permission before cloning.")
                else:
                    # Start cloning in background
                    st.session_state.cloning_progress = 10
                    st.session_state.cloning_status = "Starting cloning..."

                    thread = threading.Thread(
                        target=clone_voice_worker,
                        args=(tmp_audio_path, ref_text, target_text, speaker_name.strip() or "Authorized_Voice", True, has_permission)
                    )
                    thread.daemon = True
                    thread.start()

            # Progress
            if st.session_state.cloning_progress > 0:
                st.progress(st.session_state.cloning_progress)
                st.info(st.session_state.cloning_status)

                if st.session_state.cloning_progress == 100 and 'last_output' in st.session_state:
                    st.success("Voice cloning completed!")
                    audio_player(st.session_state.last_output)

    with tab2:
        st.markdown("### :speaking_head: Text-to-Speech")
        st.markdown("Generate speech in a saved cloned voice (Qwen3-TTS) or with gTTS")

        # Text input
        text_input = st.text_area("Enter text to generate", value="Westside till we die!", height=100)

        # Saved cloned voices
        saved_names = [v["name"] for v in st.session_state.saved_voices]
        if saved_names:
            use_saved = st.selectbox(
                "Use a saved cloned voice",
                ["(none — use engine settings below)"] + saved_names,
                help="Voices you cloned earlier are saved under models/voices/ and "
                     "can be re-used here without re-uploading.")
        else:
            use_saved = "(none — use engine settings below)"
            st.caption("No saved clones yet — clone a voice in the 'Song to Voice' tab first.")

        col1, col2 = st.columns([3, 1])

        with col1:
            # Voice settings
            if (selected_engine == "Qwen3-TTS (Advanced)"
                    and use_saved == "(none — use engine settings below)"):
                voice_description = st.text_input("Voice description",
                                                value="Warm, expressive rap vocal with confident delivery",
                                                help="Describe tone and delivery. Use only licensed artist references.")

        with col2:
            if st.button("Generate Speech", type="primary", use_container_width=True):
                if not text_input:
                    st.error("Please enter text to generate")
                else:
                    try:
                        if use_saved != "(none — use engine settings below)":
                            # Speak in a previously saved cloned voice
                            if not st.session_state.qwen_engine:
                                st.session_state.qwen_engine = Qwen3TTSEngine()
                            with st.spinner("Generating with cloned voice..."):
                                output_path = st.session_state.qwen_engine.generate_from_voice(
                                    use_saved, text_input, has_permission=True)
                            if output_path:
                                st.success(f"Speech generated in cloned voice '{use_saved}'!")
                                audio_player(output_path)
                            else:
                                st.error("Failed to generate with saved voice")

                        elif selected_engine == "gTTS (Free)":
                            # Use gTTS
                            tts = gTTS(text=text_input, lang='en')
                            output_path = os.path.join(OUT, f"gtts_output_{int(time.time())}.mp3")
                            tts.save(output_path)
                            st.success("Speech generated with gTTS!")
                            audio_player(output_path)

                        elif st.session_state.has_qwen_runtime and selected_engine == "Qwen3-TTS (Advanced)":
                            # Use Qwen3-TTS voice design
                            if not st.session_state.qwen_engine:
                                st.session_state.qwen_engine = Qwen3TTSEngine()

                            with st.spinner("Designing voice and synthesizing..."):
                                output_path = st.session_state.qwen_engine.design_voice(
                                    text=text_input,
                                    voice_description=voice_description,
                                    speaker_name="Designed_Voice",
                                    has_permission=True,
                                )

                            if output_path:
                                st.success("Speech generated with Qwen3-TTS!")
                                audio_player(output_path)
                            else:
                                st.error("Failed to generate speech")

                    except Exception as e:
                        st.error(f"Error generating speech: {e}")

    with tab3:
        st.markdown("### :robot_face: Available Models")

        models_info = []

        # Qwen3-TTS
        if st.session_state.has_qwen_runtime:
            models_info.append({
                "name": "Qwen3-TTS",
                "status": "Available",
                "features": "3-second cloning, multi-language, natural language control"
            })
        else:
            models_info.append({
                "name": "Qwen3-TTS",
                "status": "Not Installed",
                "features": "Install with: pip install qwen-tts"
            })

        # gTTS
        models_info.append({
            "name": "gTTS",
            "status": "Available",
            "features": "Free TTS, multiple languages"
        })

        # Local models
        if os.path.exists(MODELS):
            for item in os.listdir(MODELS):
                if os.path.isdir(os.path.join(MODELS, item)):
                    models_info.append({
                        "name": item,
                        "status": "Local",
                        "features": "Custom trained model"
                    })

        # Display models
        for model in models_info:
            status_emoji = "Available" if model["status"] == "Available" else "Not Available" if model["status"] == "Not Installed" else "Local"
            st.markdown(f"**{model['name']}** - {status_emoji}")
            st.markdown(f"*{model['features']}*")
            st.markdown("---")

    with tab4:
        st.markdown("### :bar_chart: Analytics")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Total Clones", "0")
            st.metric("Success Rate", "0%")
            st.metric("Avg Processing Time", "0s")

        with col2:
            st.metric("Models Loaded", "1" if st.session_state.qwen_engine else "0")
            st.metric("Advanced Engine", "Available" if st.session_state.has_qwen_runtime else "Not installed")
            st.metric("Cache Size", "0 MB")

        # Usage chart
        st.markdown("#### Usage Over Time")
        st.info("Analytics will be available after more usage")

if __name__ == "__main__":
    main()
