"""Wrapper that imports the upstream Mneme FastAPI app and mounts
the CRS REST adapter router."""

from main import app  # type: ignore[import-untyped]  # upstream Mneme app
from crs_adapter import router as crs_router  # CRS adapter

app.include_router(crs_router)
