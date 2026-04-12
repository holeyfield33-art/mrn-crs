"""Spectral signature helpers – delegates to Geometric Brain or uses a local fallback."""

from __future__ import annotations

import logging
import math
from collections import deque

import numpy as np

from src.core.models import SpectralSignature

logger = logging.getLogger(__name__)

# Golden ratio constant used by the unitarity-lab fallback
PHI = (1 + math.sqrt(5)) / 2
GOLDEN_R = 1 / PHI  # ≈ 0.618

# Fibonacci anchor sequence (first 10 terms, normalised)
_FIB_RAW = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
_FIB_SUM = sum(_FIB_RAW)
FIBONACCI_ANCHOR = np.array([f / _FIB_SUM for f in _FIB_RAW], dtype=np.float64)


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


# --------------------------------------------------------------------------- #
# Windowed spectral signature
# --------------------------------------------------------------------------- #


def compute_windowed_spectral_signature(
    embeddings: list[list[float] | np.ndarray],
    window_size: int = 50,
) -> tuple[float, float]:
    """Compute r_ratio and SHI over the most recent *window_size* embeddings.

    Returns ``(r_ratio, shi)`` computed from the covariance matrix of the
    windowed embedding set.
    """
    if not embeddings:
        return 0.0, 0.0

    window = embeddings[-window_size:]
    mat = np.array(window, dtype=np.float64)

    # Covariance matrix → eigenvalues
    if mat.shape[0] < 2:
        return 0.0, 0.0
    cov = np.cov(mat, rowvar=True)
    eigenvalues = np.linalg.eigvalsh(cov)
    eigenvalues = np.sort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[eigenvalues > 0]

    if len(eigenvalues) < 2:
        return 0.0, 0.0

    r_ratio = float(eigenvalues[1] / eigenvalues[0])
    shi = 1.0 - abs(r_ratio - GOLDEN_R)
    return round(r_ratio, 6), round(shi, 6)


def compute_shannon_entropy(eigenvalues: np.ndarray) -> float:
    """Compute Shannon entropy of a probability distribution derived from eigenvalues.

    Lower entropy indicates information collapse (repetitive / degenerate reasoning).
    """
    eigenvalues = np.asarray(eigenvalues, dtype=np.float64)
    eigenvalues = eigenvalues[eigenvalues > 0]
    if len(eigenvalues) == 0:
        return 0.0
    probs = eigenvalues / np.sum(eigenvalues)
    return float(-np.sum(probs * np.log(probs)))


def compute_entropy_from_embeddings(embeddings: list[list[float] | np.ndarray]) -> float:
    """Convenience: compute Shannon entropy of covariance eigenvalues from embeddings."""
    if len(embeddings) < 2:
        return 0.0
    mat = np.array(embeddings, dtype=np.float64)
    cov = np.cov(mat, rowvar=True)
    eigenvalues = np.linalg.eigvalsh(cov)
    return compute_shannon_entropy(eigenvalues)


def fibonacci_recovery_score(eigenvalues: np.ndarray) -> float:
    """Compute how closely the eigenvalue distribution matches the Fibonacci anchor.

    Returns a cosine similarity in [0, 1].  A score near 1 means the spectral
    shape is close to the golden-ratio ideal.
    """
    eigenvalues = np.asarray(eigenvalues, dtype=np.float64)
    eigenvalues = np.sort(eigenvalues)[::-1]
    # Truncate or pad to match anchor length
    n = len(FIBONACCI_ANCHOR)
    if len(eigenvalues) >= n:
        eig_vec = eigenvalues[:n]
    else:
        eig_vec = np.zeros(n, dtype=np.float64)
        eig_vec[: len(eigenvalues)] = eigenvalues

    eig_norm = np.linalg.norm(eig_vec)
    anchor_norm = np.linalg.norm(FIBONACCI_ANCHOR)
    if eig_norm == 0 or anchor_norm == 0:
        return 0.0
    return float(np.dot(eig_vec, FIBONACCI_ANCHOR) / (eig_norm * anchor_norm))
