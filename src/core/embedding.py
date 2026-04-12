"""Text → embedding using sentence-transformers (lazy-loaded)."""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    """Lazy-load the sentence-transformer model (cached after first call)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        logger.info("Loading embedding model %s …", _MODEL_NAME)
        return SentenceTransformer(_MODEL_NAME)
    except Exception:
        logger.warning("sentence-transformers unavailable – using random embeddings")
        return None


def embed_text(text: str) -> "NDArray[np.float32]":
    """Return a 384-dim embedding for *text*."""
    model = _get_model()
    if model is not None:
        vec = model.encode(text, convert_to_numpy=True)
        return vec.astype(np.float32)
    # Deterministic fallback based on hash for reproducibility in tests
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    return rng.standard_normal(384).astype(np.float32)
