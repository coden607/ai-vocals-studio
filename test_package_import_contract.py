from pathlib import Path


def test_ai_vocals_studio_package_marker_exists():
    marker = Path(__file__).parent / "ai_vocals_studio/__init__.py"
    assert marker.exists()
