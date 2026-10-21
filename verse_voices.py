"""Detect distinct voices across verse/turn regions in a separated vocal.

Uses the repository's neural speaker embedding backend (Resemblyzer) when
available, with the existing acoustic embedding as an explicit fallback.
Labels are anonymous voice clusters, not real-world identities.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from speaker_identity import cosine_similarity, extract_embedding


def _voiced_spans(
    y: np.ndarray,
    sr: int,
    frame_s: float = 0.5,
    min_s: float = 0.8,
) -> list[tuple[int, int]]:
    frame = max(1, int(sr * frame_s))
    spans: list[tuple[int, int]] = []
    start = None
    for i in range(0, len(y), frame):
        chunk = y[i:i + frame]
        rms = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
        voiced = rms > 0.015
        if voiced and start is None:
            start = i
        elif not voiced and start is not None:
            if i - start >= int(sr * min_s):
                spans.append((start, i))
            start = None
    if start is not None and len(y) - start >= int(sr * min_s):
        spans.append((start, len(y)))
    if not spans and y.size:
        spans.append((0, len(y)))
    return spans


def _analysis_windows(
    spans: list[tuple[int, int]],
    sr: int,
    window_s: float,
    min_window_s: float = 0.8,
) -> list[tuple[int, int]]:
    window = max(1, int(sr * window_s))
    minimum = max(1, int(sr * min_window_s))
    result: list[tuple[int, int]] = []
    for start, end in spans:
        if end - start <= window:
            if end - start >= minimum:
                result.append((start, end))
            continue
        cursor = start
        while cursor < end:
            nxt = min(end, cursor + window)
            if nxt - cursor >= minimum:
                result.append((cursor, nxt))
            cursor = nxt
    return result or spans


def _embed_clip(clip: np.ndarray, sr: int, temp_dir: Path) -> dict[str, Any]:
    """Use neural speaker embedding when installed; fallback is explicit."""
    path = temp_dir / f"turn-{len(list(temp_dir.iterdir())):04d}.wav"
    sf.write(path, clip, sr)
    return extract_embedding(path)


def _updated_centroid(current: np.ndarray, new: np.ndarray, count: int) -> np.ndarray:
    n = min(current.size, new.size)
    if n == 0:
        return new
    mixed = (current[:n] * max(1, count) + new[:n]) / float(max(1, count) + 1)
    norm = float(np.linalg.norm(mixed))
    return mixed / norm if norm > 1e-9 else mixed


def _merge_adjacent_turns(turns: list[dict[str, Any]], max_gap_s: float = 0.7) -> list[dict[str, Any]]:
    verses: list[dict[str, Any]] = []
    for turn in turns:
        if (
            verses
            and verses[-1]["voice"] == turn["voice"]
            and float(turn["start_s"]) - float(verses[-1]["end_s"]) <= max_gap_s
        ):
            verses[-1]["end_s"] = turn["end_s"]
            verses[-1]["turns"].append(turn["turn"])
            verses[-1]["confidence"] = round(
                min(float(verses[-1]["confidence"]), float(turn["confidence"])), 4
            )
            continue
        verses.append({
            "verse": len(verses) + 1,
            "voice": turn["voice"],
            "start_s": turn["start_s"],
            "end_s": turn["end_s"],
            "turns": [turn["turn"]],
            "confidence": turn["confidence"],
        })
    return verses


def distinguish_verse_voices(
    vocals_path: str | Path,
    output_dir: str | Path,
    *,
    match_threshold: float | None = None,
    window_s: float = 2.5,
) -> dict[str, Any]:
    y, sr = sf.read(str(vocals_path), dtype="float32", always_2d=False)
    if getattr(y, "ndim", 1) > 1:
        y = np.mean(y, axis=1)
    y = np.asarray(y, dtype=np.float32)

    spans = _analysis_windows(_voiced_spans(y, sr), sr, window_s)
    clusters: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    backends: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="verse-diarize-") as tmp:
        temp_dir = Path(tmp)
        for index, (start, end) in enumerate(spans, start=1):
            clip = y[start:end]
            embedded = _embed_clip(clip, sr, temp_dir)
            backend = str(embedded.get("backend") or "acoustic")
            backends.add(backend)
            emb = np.asarray(embedded.get("vector") or [], dtype=np.float64)
            threshold = float(match_threshold if match_threshold is not None else (0.63 if backend == "neural" else 0.78))

            chosen = None
            best = -1.0
            for cluster in clusters:
                if cluster["backend"] != backend:
                    continue
                score = cosine_similarity(cluster["vector"], emb)
                if score > best:
                    best = score
                    chosen = cluster

            if chosen is None or best < threshold:
                chosen = {
                    "id": f"voice_{len(clusters) + 1:02d}",
                    "vector": emb,
                    "count": 0,
                    "backend": backend,
                }
                clusters.append(chosen)
                confidence = 1.0
            else:
                confidence = max(0.0, min(1.0, (best + 1.0) / 2.0))
                chosen["vector"] = _updated_centroid(chosen["vector"], emb, chosen["count"])

            chosen["count"] += 1
            turns.append({
                "turn": index,
                "voice": chosen["id"],
                "start_s": round(start / sr, 3),
                "end_s": round(end / sr, 3),
                "similarity_to_voice": round(float(best if best >= 0 else 1.0), 4),
                "confidence": round(float(confidence), 4),
                "embedding_backend": backend,
            })

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    speaker_dir = out / "verse_voices"
    speaker_dir.mkdir(exist_ok=True)
    stems = []
    for cluster in clusters:
        mask = np.zeros_like(y)
        for turn in turns:
            if turn["voice"] != cluster["id"]:
                continue
            a = int(float(turn["start_s"]) * sr)
            b = int(float(turn["end_s"]) * sr)
            mask[a:b] = y[a:b]
        stem = speaker_dir / f"{cluster['id']}.wav"
        sf.write(stem, mask, sr)
        stems.append({
            "voice": cluster["id"],
            "turns": cluster["count"],
            "backend": cluster["backend"],
            "stem": str(stem),
        })

    verses = _merge_adjacent_turns(turns)
    primary_backend = "neural" if "neural" in backends else "acoustic"
    report = {
        "backend": f"{primary_backend}-verse-diarization",
        "identity_scope": "anonymous speaker clusters only",
        "note": (
            "Neural speaker embeddings were used where available."
            if primary_backend == "neural"
            else "Neural speaker embeddings were unavailable; acoustic clustering was used as a fallback."
        ),
        "voices": stems,
        "turns": turns,
        "verses": verses,
    }
    (out / "verse_voices.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
