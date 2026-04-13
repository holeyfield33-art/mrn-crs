"""Wrapper that imports the upstream geometric-brain-mcp FastAPI app
and mounts the CRS self-heal adapter router."""

from api import app  # type: ignore[import-untyped]  # upstream app
from self_heal import router as self_heal_router  # CRS adapter

app.include_router(self_heal_router)
