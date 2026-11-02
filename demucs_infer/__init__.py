"""Namespace package shim for external demucs_infer.
Allows importing ``demucs_infer`` as if it were a top‑level package,
by directing the package's ``__path__`` to the actual source located at
``external/demucs-infer/demucs_infer``.
"""
import pathlib
_external_path = pathlib.Path(__file__).resolve().parent.parent / "external" / "demucs-infer" / "demucs_infer"
# Expose that directory as part of this package's search path
__path__ = [str(_external_path)]

# Execute the real package's __init__ in this module's namespace so the
# top-level re-exports (DemucsSession, DemucsSeparator, separate,
# CHECKPOINT_CATALOG, __version__, ...) exist when imported through the
# shim; submodule imports alone leave them undefined. Relative imports in
# the real __init__ resolve against __path__ above.
_real_init = _external_path / "__init__.py"
exec(compile(_real_init.read_text(), str(_real_init), "exec"), globals())
