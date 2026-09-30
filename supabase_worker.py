#!/usr/bin/env python3
"""Poll Supabase voiceover jobs and run the local best-tech voice pipeline."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


DEFAULT_BUCKET = "voiceovers"
WORKER_JOB_TYPES = {
    "local_worker_voiceover",
    "local_worker_audio_replace",
    "local_worker_rvc_train",
}


def default_rvc_trainer() -> str:
    """Prefer the checked-in Applio adapter when running from the repo root."""
    adapter = Path("scripts/applio_rvc_train.sh")
    return str(adapter) if adapter.exists() else "rvc-train"


def local_storage_root() -> Path:
    return Path(
        os.environ.get("LOCAL_STORAGE_DIR")
        or Path("vercel_frontdoor/.local_voiceover_storage")
    ).resolve()


class SupabaseClient:
    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", DEFAULT_BUCKET)
        if not self.url or not self.key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        response = requests.request(method, f"{self.url}{path}", headers=headers, timeout=120, **kwargs)
        if not response.ok:
            raise RuntimeError(f"Supabase {response.status_code}: {response.text}")
        return response

    def claim_job(self) -> dict[str, Any] | None:
        response = self.request(
            "GET",
            "/rest/v1/voiceover_jobs"
            "?select=*"
            "&status=eq.queued"
            "&order=created_at.asc"
            "&limit=20",
        )
        rows = response.json()
        for job in rows:
            if str(job.get("job_type") or "") not in WORKER_JOB_TYPES:
                continue
            updated = self.update_job(job["id"], {"status": "running", "engine": "local best available"})
            return updated or job
        return None

    def update_job(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        response = self.request(
            "PATCH",
            f"/rest/v1/voiceover_jobs?id=eq.{quote(job_id)}",
            headers={"Content-Type": "application/json", "Prefer": "return=representation"},
            data=json.dumps(patch),
        )
        rows = response.json()
        return rows[0] if rows else None

    def download_object(self, object_path: str, target: Path) -> None:
        response = self.request(
            "GET",
            f"/storage/v1/object/{quote(self.bucket)}/{quote(object_path, safe='/')}",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)

    def upload_object(self, object_path: str, source: Path, content_type: str = "audio/wav") -> str:
        self.request(
            "POST",
            f"/storage/v1/object/{quote(self.bucket)}/{quote(object_path, safe='/')}",
            headers={"Content-Type": content_type, "x-upsert": "true"},
            data=source.read_bytes(),
        )
        return f"{self.url}/storage/v1/object/public/{quote(self.bucket)}/{quote(object_path, safe='/')}"


class LocalQueueClient:
    def __init__(self) -> None:
        self.root = local_storage_root()
        self.objects_dir = self.root / "objects"
        self.jobs_path = self.root / "jobs.json"
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _read_jobs(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.jobs_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []

    def _write_jobs(self, jobs: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"jobs.json.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        tmp.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        tmp.replace(self.jobs_path)

    def claim_job(self) -> dict[str, Any] | None:
        jobs = self._read_jobs()
        for index, job in enumerate(jobs):
            if job.get("status") != "queued":
                continue
            if str(job.get("job_type") or "") not in WORKER_JOB_TYPES:
                continue
            jobs[index] = {
                **job,
                "status": "running",
                "engine": "local best available",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_jobs(jobs)
            return jobs[index]
        return None

    def update_job(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        jobs = self._read_jobs()
        for index, job in enumerate(jobs):
            if str(job.get("id")) != str(job_id):
                continue
            jobs[index] = {
                **job,
                **patch,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_jobs(jobs)
            return jobs[index]
        return None

    def _object_path(self, object_path: str) -> Path:
        target = (self.objects_dir / object_path.lstrip("/")).resolve()
        if self.objects_dir.resolve() != target and self.objects_dir.resolve() not in target.parents:
            raise RuntimeError("Invalid local object path.")
        return target

    def download_object(self, object_path: str, target: Path) -> None:
        source = self._object_path(object_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def upload_object(self, object_path: str, source: Path, content_type: str = "audio/wav") -> str:
        del content_type
        target = self._object_path(object_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return f"/api/local-object?path={quote(object_path, safe='')}"


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".flac":
        return "audio/flac"
    if suffix == ".m4a":
        return "audio/mp4"
    return "audio/wav"


def _latest_rvc_model(output_dir: Path) -> Path:
    candidates = sorted(
        (path for path in output_dir.rglob("*.pth") if path.stat().st_size >= 10_000),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"RVC trainer produced no valid .pth model in {output_dir}")
    return candidates[0]


def hydrate_rvc_model(client: SupabaseClient | LocalQueueClient, profile: dict[str, Any]) -> bool:
    """Fetch a model trained by the Kaggle worker into this worker's profile."""
    name = str(profile.get("name") or "").strip()
    voice_dir = Path(profile.get("voice_dir") or Path("models") / "voices" / name)
    if not name:
        return False
    model = voice_dir / "rvc_model.pth"
    try:
        client.download_object(f"models/{name}/rvc_model.pth", model)
    except Exception:
        return False
    index = voice_dir / "rvc_model.index"
    try:
        client.download_object(f"models/{name}/rvc_model.index", index)
    except Exception:
        index = None
    profile.update({
        "rvc_available": True,
        "rvc_model": model.name,
        "rvc_index": index.name if index else None,
        "methods": {**(profile.get("methods") or {}), "rvc": True},
    })
    profile_path = voice_dir / "voice_profile.json"
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return True


def process_job(client: SupabaseClient | LocalQueueClient, job: dict[str, Any], work_root: Path) -> None:
    from clone_any_voice import convert_target_audio, synthesize_voiceover
    from voice_cloner import build_voice_profile_from_sources
    from rvc_training import (
        build_training_command,
        import_rvc_model,
        run_training_command,
        validate_training_dataset,
    )

    job_id = str(job["id"])
    voice_name = str(job.get("voice_name") or f"Queued_Voice_{job_id[:8]}")
    job_type = str(job.get("job_type") or "local_worker_voiceover")
    mode = str(job.get("mode") or "bed")
    text = str(job.get("text") or "").strip()
    settings = job.get("settings") or {}
    mood = str(settings.get("mood") or "default")
    quality_target = str(settings.get("qualityTarget") or "studio")
    if quality_target not in {"draft", "studio", "pro"}:
        quality_target = "studio"
    vocals_gain_db = float(settings.get("vocalsGainDb") or settings.get("voiceGainDb") or 0.0)
    separation = str(settings.get("separation") or os.environ.get("SONG_SEPARATION_METHOD") or "demucs")
    if separation not in {"auto", "demucs", "center"}:
        separation = "demucs"
    if quality_target in {"studio", "pro"}:
        separation = "demucs"
    input_files = job.get("input_files") or []
    if job_type == "local_worker_voiceover" and not text:
        raise RuntimeError("Queued job has no text.")
    if not input_files:
        raise RuntimeError("Queued job has no input files.")

    job_dir = work_root / job_id
    voice_dir = job_dir / "voice_sources"
    output_dir = job_dir / "outputs"
    voice_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    local_sources: list[str] = []
    for idx, item in enumerate(input_files, start=1):
        object_path = item.get("path")
        if not object_path:
            continue
        suffix = Path(str(item.get("name") or f"source_{idx}.wav")).suffix or ".wav"
        local_path = voice_dir / f"source_{idx}{suffix}"
        client.download_object(str(object_path), local_path)
        local_sources.append(str(local_path))
    if not local_sources:
        raise RuntimeError("No downloadable input files were found.")

    if job_type == "local_worker_rvc_train":
        training_report = validate_training_dataset(voice_dir, min_files=3, min_duration_s=90.0)
        client.update_job(job_id, {
            "engine": "RVC trainer",
            "report": {"stage": "dataset_validated", "training": training_report},
        })
        if not training_report["ready"]:
            raise RuntimeError("Reference set failed RVC readiness checks; upload 90+ seconds of clean voice in 3+ clips.")

        persistent_voices = Path(settings.get("voicesDir") or "models/voices")
        profile = build_voice_profile_from_sources(
            name=voice_name,
            source_paths=local_sources,
            source_type="speech",
            description=f"Queued RVC training job {job_id}",
            voices_dir=persistent_voices,
            has_permission=True,
        )
        if not profile:
            raise RuntimeError("Could not build the authorized voice profile before RVC training.")

        trainer = str(settings.get("trainer") or os.environ.get("RVC_TRAINER") or default_rvc_trainer())
        epochs = int(settings.get("epochs") or os.environ.get("RVC_TRAIN_EPOCHS") or 300)
        training_output = job_dir / "rvc_training_output"
        command = build_training_command(voice_dir, training_output, trainer=trainer, epochs=epochs)
        client.update_job(job_id, {
            "engine": f"RVC trainer ({trainer})",
            "report": {"stage": "training", "training": training_report, "command": command},
        })
        result = run_training_command(command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "RVC trainer failed")
        model = _latest_rvc_model(training_output)
        index = next(training_output.rglob("*.index"), None)
        profile = import_rvc_model(model, Path(profile["voice_dir"]), index_path=index)
        report = {
            "stage": "registered",
            "training": training_report,
            "model": str(Path(profile["voice_dir"]) / "rvc_model.pth"),
            "index": str(Path(profile["voice_dir"]) / "rvc_model.index") if index else None,
            "engine": "RVC",
        }
        client.update_job(job_id, {
            "status": "complete",
            "engine": "RVC",
            "report": report,
        })
        return

    profile = build_voice_profile_from_sources(
        name=voice_name,
        source_paths=local_sources,
        source_type="speech",
        description=f"Queued worker job {job_id}",
        voices_dir=job_dir / "voices",
        has_permission=True,
    )
    if not profile:
        raise RuntimeError("Could not build a voice profile from queued samples.")
    hydrate_rvc_model(client, profile)

    if job_type == "local_worker_audio_replace" or mode in {"song", "clip"}:
        target_meta = settings.get("targetFile") or {}
        target_object = target_meta.get("path")
        if not target_object:
            raise RuntimeError("Queued replacement job has no target audio.")
        suffix = Path(str(target_meta.get("name") or "target.wav")).suffix or ".wav"
        target_path = job_dir / f"target{suffix}"
        client.download_object(str(target_object), target_path)
        target_type = "song" if mode == "song" else "clip"
        output_audio = Path(
            convert_target_audio(
                profile,
                str(target_path),
                target_type,
                output_dir,
                vocals_gain_db,
                separation,
                quality_target,
            ) or ""
        )
    else:
        output_audio = Path(synthesize_voiceover(profile, text, output_dir, mood=mood, quality_target=quality_target) or "")
    if not output_audio.exists():
        raise RuntimeError("Local voice pipeline did not produce output audio.")

    report_path = output_dir / "quality_report.json"
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    report["quality_target"] = quality_target
    report["enforcement"] = (
        "pro-match requires strict reference quality and neural/RVC conversion for replacement jobs"
        if quality_target == "pro"
        else f"{quality_target} quality target"
    )
    storage_path = f"completed/{job_id}/{output_audio.name}"
    output_url = client.upload_object(storage_path, output_audio, _content_type(output_audio))
    client.update_job(
        job_id,
        {
            "status": "complete",
            "engine": report.get("engine") or "local best available",
            "output_path": storage_path,
            "output_url": output_url,
            "report": report,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local voiceover jobs from Supabase.")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    parser.add_argument("--poll-seconds", type=float, default=8.0)
    parser.add_argument("--work-dir", default="outputs/supabase_worker")
    args = parser.parse_args()

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        client: SupabaseClient | LocalQueueClient = SupabaseClient()
        print("Using Supabase queue/storage.")
    else:
        client = LocalQueueClient()
        print(f"Using local queue/storage at {client.root}.")
    work_root = Path(args.work_dir)
    work_root.mkdir(parents=True, exist_ok=True)

    while True:
        job = client.claim_job()
        if not job:
            if args.once:
                print("No queued jobs.")
                return 0
            time.sleep(max(1.0, args.poll_seconds))
            continue
        print(f"Processing job {job['id']}...")
        try:
            process_job(client, job, work_root)
            print(f"Completed job {job['id']}.")
        except Exception as exc:
            client.update_job(str(job["id"]), {"status": "failed", "error": str(exc)})
            print(f"Failed job {job['id']}: {exc}")
        if args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
