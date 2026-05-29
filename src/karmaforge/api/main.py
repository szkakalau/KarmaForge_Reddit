"""KarmaForge API — FastAPI application entry point.

Run:
    uvicorn karmaforge.api.main:app --reload
"""

import os
from pathlib import Path

# Load .env before any other imports that read environment variables
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8-sig") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _value = _line.partition("=")
            _key, _value = _key.strip(), _value.strip()
            if _key not in os.environ or not os.environ[_key]:
                os.environ[_key] = _value.strip('"').strip("'")

from .deps import create_app

app = create_app()
