'''FastAPI web UI for voice_on_song pipeline.

Provides a minimal HTTP API to submit a song and transcript, select a backend,
and receive the path to the generated output file.
''' 

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
import shutil
import uuid
import os
import subprocess
import sys

app = FastAPI(title="AI Vocals Studio WebUI")

# Directory to store temporary uploads and outputs
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(BASE_DIR, "tmp_uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "tmp_outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_script(song_path: str, transcript: str, backend: str) -> str:
    """Run the voice_on_song CLI and return the output file path.

    The script is assumed to be installed in the virtual environment at
    `scripts/voice_on_song.py`.
    """
    cmd = (
        f"{BASE_DIR}/venv/bin/python {BASE_DIR}/scripts/voice_on_song.py "
        f"--audio {song_path} --text \"{transcript}\" --backend {backend} "
        f"--output-dir {OUTPUT_DIR}"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"voice_on_song failed: {result.stderr}")
    # The script writes a file named <original>_output.wav (or similar). Find newest file.
    files = sorted(
        [os.path.join(OUTPUT_DIR, f) for f in os.listdir(OUTPUT_DIR)],
        key=os.path.getmtime,
        reverse=True,
    )
    if not files:
        raise RuntimeError("No output file generated")
    return files[0]

@app.post("/voice_on_song")
async def voice_on_song(
    song: UploadFile = File(...),
    transcript: str = Form(...),
    backend: str = Form("silero"),
):
    # Save uploaded song to temp file
    song_ext = os.path.splitext(song.filename)[1] or ".wav"
    song_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{song_ext}")
    with open(song_path, "wb") as f:
        shutil.copyfileobj(song.file, f)
    try:
        output_path = run_script(song_path, transcript, backend)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # Return the generated file for download
    return FileResponse(output_path, media_type="audio/wav", filename=os.path.basename(output_path))

# Optional health endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}
