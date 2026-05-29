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
            elif not os.environ[_key] and _value.strip('"').strip("'"):
                # Override empty env var with .env value
                os.environ[_key] = _value.strip('"').strip("'")
    # Mirror LLM_API_KEY → OPENAI_API_KEY for OpenAI SDK compatibility
    if os.environ.get("LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]

from .deps import create_app

app = create_app()
