from pathlib import Path


ROOT = Path(__file__).parent


def test_capabilities_endpoint_lists_the_real_engine_stack():
    source = (ROOT / "vercel_frontdoor/api/capabilities.js").read_text(encoding="utf-8")
    for name in ("ElevenLabs IVC + TTS", "Qwen3-TTS", "XTTS v2", "Demucs", "Seed-VC", "RVC + Applio", "WORLD/DSP"):
        assert name in source
    assert "ELEVENLABS_API_KEY" in source


if __name__ == "__main__":
    test_capabilities_endpoint_lists_the_real_engine_stack()
    print("Capabilities API checks passed")
