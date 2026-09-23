"""ASGI entry point: `python -m uvicorn herald.app:app --host 0.0.0.0 --port 8100`.
Open http://localhost:8100 (use a forwarded port so the browser allows the mic)."""
from .api import create_app

app = create_app()
