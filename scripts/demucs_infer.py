import pathlib
from demucs.infer import load_model, separate as demucs_separate

# Load the pre‑trained HT‑Demucs model once (CPU only)
_MODEL = load_model(name="htdemucs", device="cpu")

def separate(audio_path: str, two_stems: bool = True) -> dict:
    """Separate an audio file on CPU.

    Args:
        audio_path: Path to the input audio (wav/mp3/etc.).
        two_stems: If True, return only vocals and accompaniment.
                    If False, return the full 4‑stem dict.

    Returns:
        dict mapping stem names to absolute file paths.
    """
    audio_path = pathlib.Path(audio_path).resolve()
    out_dir = audio_path.parent / f"{audio_path.stem}_demucs_infer"
    out_dir.mkdir(exist_ok=True)

    # demucs_separate writes all stems; we keep the ones we need.
    demucs_separate(
        model=_MODEL,
        mixture_path=str(audio_path),
        out=str(out_dir),
        stem_dir="",
        split=2 if two_stems else 4,
        device="cpu",
        job_progress=False,
    )

    if two_stems:
        vocals = out_dir / "vocals.wav"
        accompaniment = out_dir / "no_vocals.wav"
        return {"vocals": str(vocals), "accompaniment": str(accompaniment)}
    else:
        return {
            "vocals": str(out_dir / "vocals.wav"),
            "drums": str(out_dir / "drums.wav"),
            "bass": str(out_dir / "bass.wav"),
            "other": str(out_dir / "other.wav"),
        }
