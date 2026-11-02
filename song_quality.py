"""Bounded, measured selection of a user's neural vocal before protected remix."""
from pathlib import Path
import json
import shutil
from uuid import uuid4

import numpy as np
import soundfile as sf
from speaker_identity import PrecisionCloneError, precision_verdict, score_identity


def _pitch_evidence(source, candidate):
    import librosa
    # Bound expensive pitch analysis; identity/audio validity cover the output.
    full, sr = librosa.load(source, sr=16000)
    rms = librosa.feature.rms(y=full)[0]
    center = int(np.argmax(rms)) * 512
    start = max(0, min(center - 7 * sr, len(full) - 15 * sr))
    a = full[start:start + 15 * sr]
    b, _ = librosa.load(candidate, sr=sr, offset=start / sr, duration=len(a) / sr)
    f, v, _ = librosa.pyin(a, sr=sr, fmin=65, fmax=1000)
    g, w, _ = librosa.pyin(b, sr=sr, fmin=65, fmax=1000)
    n = min(len(f), len(g))
    mask = v[:n] & w[:n]
    error = float(np.median(np.abs(1200 * np.log2(g[:n][mask] / f[:n][mask])))) if mask.any() else None
    return {'median_error_cents': error, 'shared_voiced_frames': int(mask.sum()),
            'analysis_seconds': min(len(a), len(b)) / sr}


def select_verified_vocal(source, profile, work_dir, convert, *, quality_target='pro', progress_cb=None):
    """Try at most three RVC retrieval settings; never change the selected speaker.

    Only a passing candidate becomes converted_vocals.wav. Failed candidates and
    the report remain explicitly diagnostic; no completed song is produced.
    """
    if quality_target not in {'best', 'studio', 'pro'}:
        raise ValueError('Verified song quality must be best, studio or pro')
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    candidates = work / '.candidates' / uuid4().hex
    candidates.mkdir(parents=True)
    source_info = sf.info(source)
    cb = progress_cb or (lambda *a: None)
    rates = (.75, .5, 1.) if profile.get('preferred_engine') == 'RVC' or profile.get('rvc_available') else (None,)
    report = {'voice': profile.get('name'), 'quality_target': quality_target,
              'vocal_modified_during_mix': False, 'attempts': [], 'verdict': None}
    selected = None
    target = profile.get('audio_profile') or {}
    ref_quality = target.get('reference_quality') or {}
    for i, rate in enumerate(rates):
        # Isolate every invocation so repeated exports cannot reuse stale audio.
        path = candidates / f'candidate_{i}.wav'
        candidate_profile = dict(profile)
        if rate is not None:
            candidate_profile.update(preferred_engine='RVC', rvc_index_rate=rate)
        attempt = {'index_rate': rate, 'path': str(path)}
        try:
            cb(f'Checking selected voice quality (candidate {i + 1}/{len(rates)})...', 45)
            ok, engine = convert(source, candidate_profile, path, work, progress_cb=cb, require_neural=True)
            if not ok:
                raise RuntimeError(engine)
            audio, sr = sf.read(path, dtype='float32', always_2d=True)
            if not audio.size or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-8:
                raise ValueError('Candidate audio is empty, silent, or non-finite')
            if np.max(np.abs(audio)) >= .999:
                raise ValueError('Candidate has no safe headroom; clipped vocals cannot pass')
            drift = abs(len(audio) / sr - source_info.duration)
            if drift > max(.05, source_info.duration * .01):
                raise ValueError('Candidate changed source timing beyond tolerance')
            pitch = _pitch_evidence(source, path)
            if pitch['shared_voiced_frames'] < 8 or pitch['median_error_cents'] is None:
                raise ValueError('Insufficient voiced frames to verify pitch preservation')
            if pitch['median_error_cents'] > 100:
                raise ValueError('Candidate changed the vocal melody beyond tolerance')
            identity = score_identity(reference_embedding=None, output_audio=path, profile=profile)
            verdict = precision_verdict(identity=identity['identity'], engine=engine,
                reference_duration_s=float(target.get('reference_duration_s') or 0),
                reference_quality=float(ref_quality.get('overall') or 0),
                quality_target='studio' if quality_target == 'best' else quality_target,
                identity_backend=identity.get('backend'))
            attempt.update(engine=engine, identity=identity, verdict=verdict, pitch=pitch, duration_drift_s=drift)
            if verdict['meets_quality_target'] and (selected is None or
                    identity['identity'] > selected['identity']['identity']):
                selected = attempt
        except (RuntimeError, ValueError, OSError) as exc:
            attempt['error'] = str(exc)
        report['attempts'].append(attempt)
        if selected and (quality_target != 'best' or selected['verdict']['meets_near_precision']):
            break
    if selected:
        report.update(verdict=selected['verdict'], selected=selected,
                      near_precision_goal_met=selected['verdict']['meets_near_precision'])
    else:
        scored = [a for a in report['attempts'] if 'identity' in a]
        if scored:
            best = max(scored, key=lambda a: a['identity']['identity'])
            report.update(verdict=best['verdict'], best_diagnostic_candidate=best)
    (work / 'quality_report.json').write_text(json.dumps(report, indent=2) + '\n')
    if not selected:
        reasons = (report['verdict'] or {}).get('reasons') or [a.get('error', 'Quality failed') for a in report['attempts']]
        raise PrecisionCloneError(f"{quality_target} target was not met. {'; '.join(reasons)}. See {work / 'quality_report.json'}")
    output = work / 'converted_vocals.wav'
    shutil.copyfile(selected['path'], output)
    return str(output), report
