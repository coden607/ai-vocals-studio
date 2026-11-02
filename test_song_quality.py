import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
import song_converter as sc


def audio(path, peak=.2):
    sf.write(path, np.full(16000, peak), 16000, subtype='FLOAT')


def test_quality_failure_never_reaches_remix(monkeypatch, tmp_path):
    from speaker_identity import PrecisionCloneError
    import song_quality as sq
    source=tmp_path/'v.wav'; audio(source)
    monkeypatch.setattr(sc,'separate_vocals',lambda *a,**k:(str(source),str(source),'demucs'))
    def reject(*a,**k): raise PrecisionCloneError('pro target was not met')
    monkeypatch.setattr(sq,'select_verified_vocal',reject)
    monkeypatch.setattr(sc,'combine_tracks',lambda *a,**k:pytest.fail('remixed unverified candidate'))
    with pytest.raises(PrecisionCloneError):
        sc.change_song(source,{'name':'selected'},tmp_path/'out',require_neural=True,quality_target='pro')


def test_search_chooses_verified_candidate_and_keeps_voice(monkeypatch,tmp_path):
    import song_quality as sq
    source=tmp_path/'source.wav'; audio(source)
    seen=[]
    def convert(src,profile,out,work,**kwargs):
        seen.append((profile['name'],profile['rvc_index_rate']))
        audio(out)
        return True,'RVC neural voice conversion'
    scores=iter([.74,.85])
    monkeypatch.setattr(sq,'score_identity',lambda **k:{'identity':next(scores),'backend':'neural+neural'})
    monkeypatch.setattr(sq,'_pitch_evidence',lambda *a:{'median_error_cents':10.,'shared_voiced_frames':40})
    p={'name':'selected','preferred_engine':'RVC','audio_profile':{'reference_duration_s':20,'reference_quality':{'overall':.8}}}
    out,report=sq.select_verified_vocal(source,p,tmp_path,convert,quality_target='pro')
    assert seen==[('selected',.75),('selected',.5)]
    assert report['verdict']['meets_near_precision']
    assert Path(out).read_bytes()==Path(report['selected']['path']).read_bytes()
    assert 'rvc_index_rate' not in p


def test_clipped_candidate_cannot_pass_identity_gate(monkeypatch,tmp_path):
    import song_quality as sq
    source=tmp_path/'source.wav'; audio(source)
    def convert(src,profile,out,work,**kwargs):
        audio(out,1.)
        return True,'Seed-VC neural conversion'
    monkeypatch.setattr(sq,'score_identity',lambda **k:pytest.fail('scored clipped audio'))
    from speaker_identity import PrecisionCloneError
    with pytest.raises(PrecisionCloneError):
        sq.select_verified_vocal(source,{'name':'selected'},tmp_path,convert)
    report=json.loads((tmp_path/'quality_report.json').read_text())
    assert 'headroom' in report['attempts'][0]['error']


def test_best_returns_highest_verified_studio_match_without_claiming_near_precision(monkeypatch,tmp_path):
    import song_quality as sq
    source=tmp_path/'source.wav'; audio(source)
    def convert(src,profile,out,work,**kwargs):
        audio(out,profile['rvc_index_rate']/4)
        return True,'RVC neural voice conversion'
    scores=iter([.74,.79,.76])
    monkeypatch.setattr(sq,'score_identity',lambda **k:{'identity':next(scores),'backend':'neural+neural'})
    monkeypatch.setattr(sq,'_pitch_evidence',lambda *a:{'median_error_cents':10.,'shared_voiced_frames':40})
    p={'name':'selected','preferred_engine':'RVC','audio_profile':{'reference_duration_s':20,'reference_quality':{'overall':.8}}}
    out,report=sq.select_verified_vocal(source,p,tmp_path,convert,quality_target='best')
    assert report['selected']['identity']['identity']==.79
    assert report['verdict']['level']=='studio'
    assert not report['near_precision_goal_met']
    assert Path(out).read_bytes()==Path(report['selected']['path']).read_bytes()


def test_successful_quality_selection_reaches_protected_mixer_without_vocal_changes(monkeypatch,tmp_path):
    import song_quality as sq
    source=tmp_path/'v.wav'; beat=tmp_path/'beat.wav'
    audio(source); audio(beat,.1)
    monkeypatch.setattr(sc,'separate_vocals',lambda *a,**k:(str(source),str(beat),'demucs'))
    def verified(src,profile,work,*args,**kw):
        out=Path(work)/'converted_vocals.wav'; out.write_bytes(source.read_bytes())
        return str(out),{'selected':{'engine':'RVC','identity':{'identity':.9}},'verdict':{'level':'near_precision'}}
    monkeypatch.setattr(sq,'select_verified_vocal',verified)
    out,steps=sc.change_song(source,{'name':'selected'},tmp_path/'out',require_neural=True,quality_target='best')
    mixed,sr=sf.read(out,always_2d=True)
    adapted,_=sf.read(steps['adapted_beat'],always_2d=True)
    original,_=sf.read(source,always_2d=True)
    np.testing.assert_allclose(mixed-adapted,original,atol=8e-8)
    assert (tmp_path/'out/converted_vocals.wav').read_bytes()==source.read_bytes()
    assert steps['quality_level']=='near_precision'


def test_repeated_selection_cannot_reuse_stale_candidate(monkeypatch,tmp_path):
    import song_quality as sq
    source=tmp_path/'source.wav'; audio(source)
    monkeypatch.setattr(sq,'score_identity',lambda **k:{'identity':.9,'backend':'neural+neural'})
    monkeypatch.setattr(sq,'_pitch_evidence',lambda *a:{'median_error_cents':10.,'shared_voiced_frames':40})
    p={'name':'selected','audio_profile':{'reference_duration_s':20,'reference_quality':{'overall':.8}}}
    def convert(src,profile,out,work,**kwargs):
        audio(out)
        return True,'RVC'
    sq.select_verified_vocal(source,p,tmp_path,convert)
    from speaker_identity import PrecisionCloneError
    with pytest.raises(PrecisionCloneError):
        sq.select_verified_vocal(source,p,tmp_path,lambda *a,**k:(True,'RVC'))
