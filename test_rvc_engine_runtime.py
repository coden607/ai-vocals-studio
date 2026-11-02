from pathlib import Path
import numpy as np
import soundfile as sf
import rvc_engine as engine


def test_rvc_load_passes_retrieval_index_to_backend(monkeypatch, tmp_path):
    voice = tmp_path / 'authorized'
    voice.mkdir()
    (voice / 'rvc_model.pth').write_bytes(b'x' * 10001)
    index = voice / 'rvc_model.index'
    index.write_bytes(b'index')
    seen = {}

    class Backend:
        def __init__(self, **kwargs): pass
        def load_model(self, path, **kwargs): seen.update(kwargs)
        def set_params(self, **kwargs):
            assert 'index_path' not in kwargs

    monkeypatch.setattr(engine, '_ensure_rvc', lambda *_: True)
    monkeypatch.setattr(engine, '_rvc_module', Backend)
    ok, msg = engine.RvcEngine(tmp_path).load('authorized', device='cpu')
    assert ok, msg
    assert seen['index_path'] == str(index)


def test_rvc_rejects_undecodable_backend_output(monkeypatch, tmp_path):
    runner = engine.RvcEngine(tmp_path)
    class Backend:
        def set_params(self, **kwargs): pass
        def infer_file(self, source, output): Path(output).write_bytes(b'x' * 1024)
    runner._rvc = Backend()
    monkeypatch.setattr(runner, 'load', lambda *a, **kw: (True, ''))
    ok, message = runner.convert('authorized', 'source.wav', tmp_path / 'out.wav')
    assert not ok
    assert 'audio' in message.lower()


def test_rvc_preserves_native_rate_and_duration(monkeypatch, tmp_path):
    runner = engine.RvcEngine(tmp_path)
    # rvc-python resamples to resample_sr but writes the model's native WAV
    # rate. Requesting 44.1 kHz for a 48 kHz model changes timing and pitch.
    class Backend:
        def set_params(self, **kwargs): self.params = kwargs
        def infer_file(self, source, output):
            frames = self.params['resample_sr'] or 48000
            sf.write(output, np.full(frames, 0.1), 48000)
    runner._rvc = Backend()
    monkeypatch.setattr(runner, 'load', lambda *a, **kw: (True, ''))
    ok, message = runner.convert('authorized', 'source.wav', tmp_path / 'out.wav')
    assert ok, message
    info = sf.info(tmp_path / 'out.wav')
    assert info.duration == 1.0
