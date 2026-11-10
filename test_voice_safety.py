import pytest

from voice_safety import VoiceSafetyError, validate_voice_clone_request


def test_clone_requires_permission():
    with pytest.raises(VoiceSafetyError):
        validate_voice_clone_request(has_permission=False, speaker_name="pacaveli")


def test_clone_requires_speaker_name():
    with pytest.raises(VoiceSafetyError):
        validate_voice_clone_request(has_permission=True, speaker_name="  ")


def test_named_authorized_speaker_passes():
    validate_voice_clone_request(has_permission=True, speaker_name="pacaveli")
