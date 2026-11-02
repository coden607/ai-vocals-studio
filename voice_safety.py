"""Consent checks for voice cloning workflows."""
from __future__ import annotations


class VoiceSafetyError(ValueError):
    """Raised when a requested voice operation is not allowed."""


def validate_voice_clone_request(
    *,
    has_permission: bool,
    speaker_name: object = "",
    description: object = "",
    source_path: object = "",
    voice_description: object = "",
) -> None:
    """Validate that the caller confirmed voice rights/permission."""
    if not has_permission:
        raise VoiceSafetyError(
            "Voice cloning requires explicit permission from the speaker or a valid license."
        )
    if not str(speaker_name or "").strip():
        raise VoiceSafetyError("A speaker or voice name is required before cloning.")
