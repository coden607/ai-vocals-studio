"""Stub for Qwen3 backend.

The original implementation required heavy native dependencies that are not
available in this CPU‑only environment. To keep the package functional we
provide a minimal stub that raises ``NotImplementedError`` when invoked.
"""

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Placeholder for Qwen3 voice cloning.

    This stub deliberately does not attempt any processing and informs the
    caller that the backend is unavailable.
    """
    raise NotImplementedError(
        "Qwen3 backend is disabled due to missing native dependencies. Use the Coqui backend instead."
    )
