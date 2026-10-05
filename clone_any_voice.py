#!/usr/bin/env python3
"""Unified authorized voice cloning, conversion, and voice-over CLI."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np


def _progress(msg: str, pct: int) -> None:
    pct = max(0, min(100, int(pct)))
    print(f"[{pct:3d}%] {msg}")


def _load_profile(profile_or_name: str) -> dict:
    from voice_cloner import DEFAULT_VOICES_DIR, load_voice_profile

    path = Path(profile_or_name).expanduser()
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            profile = json.load(f)
        profile.setdefault("voice_dir", str(path.parent))
        return profile

    profile = load_voice_profile(profile_or_name, DEFAULT_VOICES_DIR)
    if profile:
        return profile
    raise FileNotFoundError(f"Voice profile not found: {profile_or_name}")


def build_profile(args: argparse.Namespace) -> dict:
    if args.profile:
        return _load_profile(args.profile)

    if not args.voice_source:
        raise ValueError("Provide --voice-source or --profile.")

    from voice_cloner import build_voice_profile_from_sources

    profile = build_voice_profile_from_sources(
        name=args.name,
        source_paths=args.voice_source,
        source_type=args.voice_source_type,
        description=args.description,
        progress_cb=_progress,
        has_permission=args.i_have_permission,
    )
    if not profile:
        raise RuntimeError("Voice profile build failed.")
    return profile


def _configured_path(path: Path) -> Path | None:
    if not path.exists():
        return None
    value = path.read_text(errors="ignore").strip()
    if not value:
        return None
    if "=" in value:
        value = value.split("=", 1)[1].strip()
    return Path(value)


def _sidecar_python(engine: str | None = None) -> Path | None:
    override = os.environ.get("VOICE_ENGINE_SIDECAR", "").strip()
    candidates = [Path(override)] if override else []
    cfg_names = []
    if engine == "rvc":
        cfg_names.append(".rvc_engine_sidecar")
    if engine == "xtts":
        cfg_names.append(".xtts_engine_sidecar")
    cfg_names.append(".voice_engine_sidecar")
    for cfg_name in cfg_names:
        configured = _configured_path(Path(cfg_name))
        if configured:
            candidates.append(configured)
    if engine == "rvc":
        candidates.append(Path("venv_rvc_engines/bin/python"))
    if engine == "xtts":
        candidates.append(Path("venv_xtts_engines/bin/python"))
    candidates.extend([Path("venv_voice_engines/bin/python"), Path(".venv_voice_engines/bin/python")])
    for path in candidates:
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


def _run_sidecar(args: list[str], timeout: int = 900) -> dict:
    python = _sidecar_python(args[0] if args else None)
    if not python:
        raise RuntimeError("voice engine sidecar is not configured")
    result = subprocess.run(
        [str(python), "voice_engine_sidecar.py", *args],
        cwd=str(Path.cwd()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    payload = {}
    for line in reversed((result.stdout or "").splitlines()):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if result.returncode != 0 or not payload.get("ok"):
        err = payload.get("error") or payload.get("message") or result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(err or "sidecar engine failed")
    return payload


def convert_target_audio(
    profile: dict,
    target_audio: str,
    target_type: str,
    output_dir: Path,
    vocals_gain_db: float,
    separation: str = "demucs",
    quality_target: str = "studio",
) -> Optional[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    from engine_planner import choose_best_plan

    plan_mode = "song" if target_type == "song" else "clip"
    if target_type == "song":
        from song_converter import change_song, write_conversion_report
        plan = choose_best_plan(profile=profile, mode=plan_mode, target_has_voice=True)
        print(f"[ok] selected engine plan: {plan['engine']} ({plan['confidence']}% confidence)")
        # Songs always follow separate -> convert isolated vocal -> remix over
        # the untouched separated instrumental. Studio/Pro never permit a
        # center-channel or DSP-only shortcut.
        out, steps = change_song(
            target_audio,
            profile,
            output_dir,
            progress_cb=_progress,
            separation=separation,
            vocals_gain_db=vocals_gain_db,
            require_neural=quality_target in {"studio", "pro"},
        )
        print(f"[ok] song conversion engine: {steps.get('conversion')}")
        score_path = output_dir / "converted_vocals.wav"
        if score_path.exists():
            score = print_accuracy_score(profile, score_path, engine=str(steps.get("conversion", "")), quality_target=quality_target)
            report = write_conversion_report(
                output_dir / "quality_report.json",
                profile=profile,
                source_audio=target_audio,
                output_audio=out,
                engine=str(steps.get("conversion", "unknown")),
                score=score,
                plan=plan,
            )
            print(f"[ok] quality report: {report}")
        return out

    from song_converter import _load_mono, convert_vocals, voiced_fraction, write_conversion_report

    y = _load_mono(target_audio, 22050)
    voice_fraction = voiced_fraction(y, 22050)
    has_voice = voice_fraction >= 0.08
    plan = choose_best_plan(profile=profile, mode=plan_mode, target_has_voice=has_voice)
    print(f"[ok] selected engine plan: {plan['engine']} ({plan['confidence']}% confidence)")
    if quality_target == "pro" and plan.get("engine") != "RVC":
        raise RuntimeError(
            "Pro-match clip conversion requires a trained RVC model for this voice. "
            "Add rvc_model.pth to the voice profile directory or lower quality target to Studio/Draft."
        )
    if not has_voice:
        raise ValueError(
            "Target audio has little or no detectable voice. Use --target-type bed "
            "with --voiceover-text to place the cloned voice over a beat/instrumental."
        )

    stem = Path(target_audio).stem.replace(" ", "_")
    out_path = output_dir / f"{stem}_in_{profile.get('name', 'voice')}.wav"
    ok, msg = convert_vocals(
        target_audio,
        profile,
        out_path,
        output_dir,
        progress_cb=_progress,
    )
    if not ok:
        raise RuntimeError(msg)
    print(f"[ok] audio conversion engine: {msg}")
    score = print_accuracy_score(profile, out_path, engine=msg, quality_target=quality_target)
    print(f"[ok] source voiced frames: {round(voice_fraction * 100.0, 1)}%")
    report = write_conversion_report(
        output_dir / "quality_report.json",
        profile=profile,
        source_audio=target_audio,
        output_audio=out_path,
        engine=msg,
        score=score,
        plan=plan,
    )
    print(f"[ok] quality report: {report}")
    return str(out_path)


def score_voice_accuracy(profile: dict, audio_path: str | Path, engine: str | None = None, quality_target: str = "studio") -> dict:
    """Score speaker identity. The old pitch/timbre number is kept as a legacy field only."""
    from song_converter import _load_mono, band_energy_profile, estimate_pitch
    from speaker_identity import precision_verdict, score_identity

    target = profile.get("audio_profile", {})
    y = _load_mono(audio_path, 22050)
    if y.size == 0:
        return {"score": 0.0, "identity": 0.0, "pitch": 0.0, "timbre": 0.0, "energy": 0.0, "legacy_heuristic": 0.0}

    ref_f0 = float(target.get("median_f0_hz", 0.0) or 0.0)
    out_f0, _ = estimate_pitch(y, 22050)
    if ref_f0 > 40 and out_f0 > 40:
        pitch_score = 1.0 - min(abs(np.log2(out_f0 / ref_f0)) / 1.0, 1.0)
    else:
        pitch_score = 0.35

    ref_env = np.asarray(target.get("spectral_envelope") or [], dtype=np.float64)
    out_env = np.asarray(band_energy_profile(y, 22050, n_bands=16), dtype=np.float64)
    if ref_env.size == out_env.size and ref_env.size:
        ref_env = ref_env - np.mean(ref_env)
        out_env = out_env - np.mean(out_env)
        denom = (np.linalg.norm(ref_env) * np.linalg.norm(out_env)) + 1e-9
        timbre_score = float((np.dot(ref_env, out_env) / denom + 1.0) / 2.0)
    else:
        timbre_score = 0.35

    ref_rms = float(target.get("rms", 0.0) or 0.0)
    out_rms = float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0
    if ref_rms > 1e-6 and out_rms > 1e-6:
        energy_score = 1.0 - min(abs(np.log10(out_rms / ref_rms)) / 1.5, 1.0)
    else:
        energy_score = 0.35

    legacy = 100.0 * (
        0.45 * max(0.0, pitch_score)
        + 0.45 * max(0.0, timbre_score)
        + 0.10 * max(0.0, energy_score)
    )
    identity = score_identity(reference_embedding=None, output_audio=audio_path, profile=profile)
    duration = float(target.get("reference_duration_s", target.get("duration_s", 0.0)) or 0.0)
    quality = target.get("reference_quality") or {}
    quality_score = float(quality.get("overall", target.get("average_source_quality", 0.0)) or 0.0)
    verdict = precision_verdict(
        identity=float(identity.get("identity") or 0.0),
        engine=engine,
        reference_duration_s=duration,
        reference_quality=quality_score,
        quality_target=quality_target,
        identity_backend=identity.get("backend"),
    )
    return {
        "score": identity.get("identity_pct", 0.0),
        "identity": identity.get("identity", 0.0),
        "identity_backend": identity.get("backend"),
        "precision": verdict,
        "legacy_heuristic": round(float(np.clip(legacy, 0.0, 100.0)), 1),
        "pitch": round(float(np.clip(pitch_score * 100.0, 0.0, 100.0)), 1),
        "timbre": round(float(np.clip(timbre_score * 100.0, 0.0, 100.0)), 1),
        "energy": round(float(np.clip(energy_score * 100.0, 0.0, 100.0)), 1),
        "confidence": round(min(100.0, duration / 60.0 * 100.0), 1),
    }


def print_accuracy_score(profile: dict, audio_path: str | Path, engine: str | None = None, quality_target: str = "studio") -> dict:
    score = score_voice_accuracy(profile, audio_path, engine=engine, quality_target=quality_target)
    verdict = score.get("precision") or {}
    print(
        "[ok] speaker identity: "
        f"{verdict.get('identity_used')} used "
        f"(raw={score.get('identity')} backend={score.get('identity_backend')}) "
        f"verdict={verdict.get('level')} "
        f"meets_{quality_target}={verdict.get('meets_quality_target')}"
    )
    print(
        "[note] legacy pitch/timbre heuristic: "
        f"{score.get('legacy_heuristic')}%. It is not a clone score."
    )
    from speaker_identity import enforce_quality_target
    enforce_quality_target(verdict, quality_target)
    return score


def synthesize_voiceover(
    profile: dict,
    text: str,
    output_dir: Path,
    mood: str = "default",
    quality_target: str = "studio",
) -> Optional[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    name = str(profile.get("name") or "cloned_voice")
    reference = profile.get("reference")
    failures: list[str] = []
    candidates: list[dict] = []
    from engine_planner import choose_best_plan

    plan = choose_best_plan(profile=profile, mode="bed", target_has_voice=False)
    print(f"[ok] selected voice-over plan: {plan['engine']} ({plan['confidence']}% confidence)")

    def add_candidate(engine: str, path: str | Path) -> None:
        candidate_path = Path(path)
        if not candidate_path.exists() or candidate_path.stat().st_size < 100:
            failures.append(f"{engine}: empty output")
            return
        score = score_voice_accuracy(profile, candidate_path, engine=engine, quality_target=quality_target)
        verdict = (score.get("precision") or {}).get("level")
        print(
            f"[ok] candidate: {engine} identity={score.get('identity')} "
            f"verdict={verdict} legacy={score.get('legacy_heuristic')}%"
        )
        candidates.append({
            "engine": engine,
            "path": str(candidate_path),
            "score": score,
            "polished": False,
        })

    def add_polished_candidates() -> None:
        from song_converter import convert_vocals

        originals = list(candidates)
        for idx, item in enumerate(originals, start=1):
            if "DSP" in item["engine"] or "RVC polish" in item["engine"]:
                continue
            source = Path(item["path"])
            polished = output_dir / f"{source.stem}_voice_profile_polish_{idx}.wav"
            try:
                ok, msg = convert_vocals(source, profile, polished, output_dir, progress_cb=_progress)
                if ok:
                    score = score_voice_accuracy(profile, polished, engine=f"{item['engine']} + {msg}", quality_target=quality_target)
                    engine = f"{item['engine']} + {msg}"
                    print(
                        f"[ok] polished candidate: {engine} identity={score.get('identity')} "
                        f"verdict={(score.get('precision') or {}).get('level')}"
                    )
                    candidates.append({
                        "engine": engine,
                        "path": str(polished),
                        "score": score,
                        "polished": True,
                        "source_engine": item["engine"],
                    })
            except Exception as exc:
                failures.append(f"{item['engine']} polish: {exc}")

    try:
        from elevenlabs_engine import ElevenLabsEngine

        el = ElevenLabsEngine(Path.cwd())
        dataset_dir = Path("dataset") / name
        if el.can_synthesize() and dataset_dir.is_dir():
            out = el.synthesize(text, name, mood=mood, progress_cb=_progress)
            final = output_dir / f"{name}_voiceover_elevenlabs.wav"
            shutil.copy2(out, final)
            print("[ok] voice-over engine: ElevenLabs")
            add_candidate("ElevenLabs", final)
    except Exception as e:
        failures.append(f"ElevenLabs: {e}")

    if reference and Path(reference).exists():
        try:
            from qwen3_tts_engine import Qwen3TTSEngine

            qe = Qwen3TTSEngine()
            if qe.can_clone():
                out = output_dir / f"{name}_voiceover_qwen.wav"
                result = qe.clone_voice(
                    ref_audio=reference,
                    ref_text=None,
                    target_text=text,
                    speaker_name=name,
                    output_path=out,
                    progress_cb=_progress,
                    has_permission=True,
                )
                if result:
                    print("[ok] voice-over engine: Qwen3-TTS")
                    add_candidate("Qwen3-TTS", result)
        except Exception as e:
            failures.append(f"Qwen3-TTS: {e}")

        try:
            from xtts_engine import XttsEngine

            xtts = XttsEngine(Path.cwd())
            if xtts.can_synthesize():
                out = xtts.synthesize(
                    text,
                    name,
                    mood=mood,
                    custom_ref=reference,
                    progress_cb=_progress,
                )
                final = output_dir / f"{name}_voiceover_xtts.wav"
                shutil.copy2(out, final)
                print("[ok] voice-over engine: XTTS v2")
                add_candidate("XTTS v2", final)
        except Exception as e:
            failures.append(f"XTTS: {e}")

        try:
            final = output_dir / f"{name}_voiceover_xtts_sidecar.wav"
            _run_sidecar([
                "xtts",
                "--text", text,
                "--voice-name", name,
                "--reference", str(reference),
                "--mood", mood,
                "--output", str(final),
            ])
            print("[ok] voice-over engine: XTTS v2 sidecar")
            add_candidate("XTTS v2 sidecar", final)
        except Exception as e:
            failures.append(f"XTTS sidecar: {e}")

    if quality_target != "pro":
        try:
            from gtts import gTTS
            from song_converter import convert_vocals

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tts_path = Path(tmp.name)
            gTTS(text=text, lang="en").save(str(tts_path))
            out = output_dir / f"{name}_voiceover_dsp.wav"
            convert_vocals(tts_path, profile, out, output_dir, progress_cb=_progress)
            print("[ok] voice-over engine: gTTS + DSP timbre mapping")
            add_candidate("gTTS + DSP", out)
        except Exception as e:
            failures.append(f"gTTS+DSP: {e}")
    else:
        failures.append("gTTS+DSP: disabled in Pro-match mode")

    if candidates:
        add_polished_candidates()

    if not candidates:
        raise RuntimeError("No voice-over backend succeeded: " + " | ".join(failures))

    def _rank(item: dict) -> tuple:
        verdict = item["score"].get("precision") or {}
        return (
            1 if verdict.get("meets_quality_target") else 0,
            float(item["score"].get("identity") or 0.0),
        )
    best = max(candidates, key=_rank)
    final = output_dir / f"{name}_voiceover_best.wav"
    shutil.copy2(best["path"], final)
    print(f"[ok] selected best take: {best['engine']}")
    score = print_accuracy_score(profile, final, engine=str(best["engine"]), quality_target=quality_target)
    write_voiceover_report(
        output_dir / "quality_report.json",
        profile,
        final,
        str(best["engine"]),
        score,
        plan,
        candidates=candidates,
        failures=failures,
    )
    return str(final)


def write_voiceover_report(
    report_path: str | Path,
    profile: dict,
    output_audio: str | Path,
    engine: str,
    score: dict,
    plan: dict | None = None,
    candidates: list[dict] | None = None,
    failures: list[str] | None = None,
) -> str:
    from song_converter import write_conversion_report

    report = write_conversion_report(
        report_path,
        profile=profile,
        source_audio=profile.get("reference", ""),
        output_audio=output_audio,
        engine=engine,
        score=score,
        plan=plan,
    )
    if candidates is not None or failures is not None:
        path = Path(report)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["candidate_takes"] = [
            {
                "engine": item.get("engine"),
                "output_audio": item.get("path"),
                "estimated_accuracy": item.get("score"),
                "polished": bool(item.get("polished", False)),
                "source_engine": item.get("source_engine"),
            }
            for item in (candidates or [])
        ]
        data["failed_backends"] = failures or []
        data["selection"] = {
            "strategy": "highest estimated voice match across generated and polished candidates",
            "selected_engine": engine,
            "selected_output": str(output_audio),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[ok] quality report: {report}")
    return report


def mix_voiceover_over_bed(
    voiceover_path: str | Path,
    bed_path: str | Path,
    output_path: str | Path,
    voice_gain_db: float = 0.0,
    bed_gain_db: float = -3.0,
) -> str:
    """Mix a generated cloned voice-over over a beat/instrumental bed."""
    import librosa
    import soundfile as sf

    bed, bed_sr = sf.read(str(bed_path), dtype="float32", always_2d=True)
    voice, _ = librosa.load(str(voiceover_path), sr=bed_sr, mono=True)
    voice = voice.astype("float32")
    if voice.ndim == 1:
        voice = np.stack([voice, voice], axis=1)

    n = max(len(bed), len(voice))
    if len(bed) < n:
        bed = np.pad(bed, ((0, n - len(bed)), (0, 0)))
    if len(voice) < n:
        voice = np.pad(voice, ((0, n - len(voice)), (0, 0)))

    voice_gain = 10.0 ** (voice_gain_db / 20.0)
    bed_gain = 10.0 ** (bed_gain_db / 20.0)
    mixed = bed[:n] * bed_gain + voice[:n] * voice_gain
    peak = np.max(np.abs(mixed)) or 1.0
    if peak > 0.98:
        mixed = mixed / peak * 0.98

    sf.write(str(output_path), mixed.astype("float32"), bed_sr)
    return str(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone an authorized voice from audio/training data, then convert audio or generate voice-over."
    )
    parser.add_argument("--voice-source", action="append", default=[], help="voice source file/folder; repeat for multiple")
    parser.add_argument("--voice-source-type", choices=["speech", "song", "text"], default="speech")
    parser.add_argument("--profile", help="existing profile JSON path or saved voice name")
    parser.add_argument("--name", default=f"cloned_voice_{int(time.time())}")
    parser.add_argument("--description", default="")
    parser.add_argument("--target-audio", help="audio/song to make sound like the cloned voice")
    parser.add_argument("--target-type", choices=["clip", "song", "bed"], default="clip")
    parser.add_argument("--voiceover-text", help="text to synthesize in the cloned voice")
    parser.add_argument("--mood", default="default")
    parser.add_argument("--output-dir", default="outputs/clone_any_voice")
    parser.add_argument("--vocals-gain-db", type=float, default=0.0)
    parser.add_argument(
        "--separation",
        choices=["auto", "demucs", "center"],
        default=os.environ.get("SONG_SEPARATION_METHOD", "demucs"),
        help="song vocal separation method; Demucs is the production default and runs before any voice conversion",
    )
    parser.add_argument("--quality-target", choices=["draft", "studio", "pro"], default="studio")
    parser.add_argument(
        "--i-have-permission",
        action="store_true",
        help="confirm you own the voice or have explicit written permission/license to use it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.i_have_permission:
        print("[error] pass --i-have-permission to confirm authorization for this voice.")
        return 1
    if not args.target_audio and not args.voiceover_text:
        print("[error] provide --target-audio and/or --voiceover-text.")
        return 1

    try:
        output_dir = Path(args.output_dir)
        profile = build_profile(args)
        print(f"[ok] voice profile: {profile.get('name')} ({profile.get('reference')})")

        voiceover_out: Optional[str] = None
        if args.voiceover_text:
            voiceover_out = synthesize_voiceover(
                profile,
                args.voiceover_text,
                output_dir,
                args.mood,
                args.quality_target,
            )
            print(f"[ok] voice-over: {voiceover_out}")

        if args.target_audio and args.target_type == "bed":
            if not voiceover_out:
                raise ValueError("--target-type bed requires --voiceover-text.")
            mixed = output_dir / f"{profile.get('name', 'voice')}_voiceover_mix.wav"
            out = mix_voiceover_over_bed(
                voiceover_out,
                args.target_audio,
                mixed,
                voice_gain_db=args.vocals_gain_db,
            )
            print(f"[ok] voice-over mixed over bed: {out}")

        elif args.target_audio:
            out = convert_target_audio(
                profile,
                args.target_audio,
                args.target_type,
                output_dir,
                args.vocals_gain_db,
                args.separation,
                args.quality_target,
            )
            print(f"[ok] converted audio: {out}")

        return 0
    except Exception as e:
        print(f"[error] {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
