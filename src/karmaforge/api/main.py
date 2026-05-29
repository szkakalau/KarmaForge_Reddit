"""KarmaForge API — FastAPI application entry point.

Run:
    uvicorn karmaforge.api.main:app --reload
"""

from .deps import create_app

app = create_app()
