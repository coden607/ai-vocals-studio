"""Split a separated vocal into verse-level speaker turns.

This is not a studio diarizer. It groups voiced spans whose acoustic
embeddings match, so a song can report which verse voice is which before
a clone is remixed over the beat.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from speaker_identity import acoustic_embedding, cosine_similarity


def _voiced_spans(y: np.ndarray, sr: int, frame_s: float = 0.5, min_s: float = 0.8) -> list[tuple[int, int]]:
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


def distinguish_verse_voices(
    vocals_path: str | Path,
    output_dir: str | Path,
    *,
    match_threshold: float = 0.72,
) -> dict[str, Any]:
    y, sr = sf.read(str(vocals_path), dtype="float32", always_2d=False)
    if getattr(y, "ndim", 1) > 1:
        y = np.mean(y, axis=1)
    y = np.asarray(y, dtype=np.float32)
    spans = _voiced_spans(y, sr)
    window = int(sr * 1.5)
    windowed: list[tuple[int, int]] = []
    for start, end in spans:
        if end - start <= window:
            windowed.append((start, end))
            continue
        cursor = start
        while cursor < end:
            nxt = min(end, cursor + window)
            if nxt - cursor >= int(sr * 0.6):
                windowed.append((cursor, nxt))
            cursor = nxt
    spans = windowed or spans
    clusters: list[dict[str, Any]] = []
    turns = []
    for index, (start, end) in enumerate(spans, start=1):
        clip = y[start:end]
        emb = acoustic_embedding(clip, sr)
        chosen = None
        best = -1.0
        for cluster in clusters:
            score = cosine_similarity(cluster["vector"], emb)
            if score > best:
                best = score
                chosen = cluster
        if chosen is None or best < match_threshold:
            chosen = {"id": f"voice_{len(clusters) + 1:02d}", "vector": emb, "count": 0}
            clusters.append(chosen)
        chosen["count"] += 1
        turns.append({
            "turn": index,
            "voice": chosen["id"],
            "start_s": round(start / sr, 3),
            "end_s": round(end / sr, 3),
            "similarity_to_voice": round(float(best if best >= 0 else 1.0), 4),
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
            a = int(turn["start_s"] * sr)
            b = int(turn["end_s"] * sr)
            mask[a:b] = y[a:b]
        stem = speaker_dir / f"{cluster['id']}.wav"
        sf.write(stem, mask, sr)
        stems.append({"voice": cluster["id"], "turns": cluster["count"], "stem": str(stem)})

    report = {
        "backend": "acoustic-verse-cluster",
        "note": "Groups verse spans by acoustic similarity. Install Resemblyzer for a neural speaker check before treating labels as identity.",
        "voices": stems,
        "turns": turns,
    }
    (out / "verse_voices.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
