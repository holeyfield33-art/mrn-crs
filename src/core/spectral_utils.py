"""Spectral signature helpers – delegates to Geometric Brain or uses a local fallback."""

from __future__ import annotations

import logging
import math

import numpy as np

from src.core.models import SpectralSignature

logger = logging.getLogger(__name__)

# Golden ratio constant used by the unitarity-lab fallback
PHI = (1 + math.sqrt(5)) / 2
GOLDEN_R = 1 / PHI  # ≈ 0.618


def local_spectral_signature(embedding: np.ndarray) -> SpectralSignature:
    """Compute a lightweight spectral signature locally (unitarity-lab fallback).

    * r_ratio  – ratio of top-2 singular values of a reshaped embedding matrix
    * SHI      – 1 − |r_ratio − GOLDEN_R|  (closer to 1 is healthier)
    """
    side = int(math.sqrt(len(embedding)))
    if side * side != len(embedding):
        # Pad to nearest square
        side = int(math.ceil(math.sqrt(len(embedding))))
        padded = np.zeros(side * side, dtype=np.float32)
        padded[: len(embedding)] = embedding
        embedding = padded
    mat = embedding.reshape(side, side)
    svs = np.linalg.svd(mat, compute_uv=False)
    if len(svs) < 2 or svs[0] == 0:
        return SpectralSignature(r_ratio=0.0, shi=0.0, unitarity_check=False)
    r_ratio = float(svs[1] / svs[0])
    shi = 1.0 - abs(r_ratio - GOLDEN_R)
    unitarity = 0.55 <= r_ratio <= 0.65
    return SpectralSignature(r_ratio=round(r_ratio, 6), shi=round(shi, 6), unitarity_check=unitarity)
