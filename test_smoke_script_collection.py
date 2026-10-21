import ast
from pathlib import Path


def test_voice_clone_smoke_script_does_not_import_runtime_at_collection_time():
    source = Path("scripts/test_voice_cloning.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            (alias.name if isinstance(node, ast.Import) else node.module or "").startswith("ai_vocals_studio")
            for alias in getattr(node, "names", [])
        )
    ]
    assert not top_level_imports
    assert "from ai_vocals_studio.voice_cloning import clone_voice" in source
