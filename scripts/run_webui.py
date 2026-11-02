import sys
from pathlib import Path

# Ensure repository root is on sys.path for imports
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("scripts.webui:app", host="0.0.0.0", port=8000)
