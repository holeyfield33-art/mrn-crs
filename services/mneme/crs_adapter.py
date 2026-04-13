"""CRS REST adapter for Mneme.

Adds /memory/* endpoints that the CRS orchestrator expects, backed by
Mneme's asyncpg storage layer.  A separate ``crs_embedding`` column
(384-dim) is used to avoid clashing with Mneme's native 1536-dim OpenAI
embeddings.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Fixed namespace used by CRS in personal-mode deployments
CRS_NAMESPACE = "ns_crs"

_schema_ready = False


async def _get_conn():
    """Yield a raw asyncpg connection from Mneme's pool."""
    import db as database  # type: ignore[import-untyped]
    async with database.pool.acquire() as conn:
        yield conn


async def _ensure_schema(conn) -> None:
    """Lazily add CRS-specific columns to the memories table."""
    global _schema_ready
    if _schema_ready:
        return
    # Check if the memories table exists yet (upstream Mneme creates it lazily)
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'memories')"
    )
    if not exists:
        return  # table will be created by upstream Mneme on first use
    await conn.execute("""
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS crs_embedding vector(384);
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS r_ratio DOUBLE PRECISION;
        ALTER TABLE memories ADD COLUMN IF NOT EXISTS shi DOUBLE PRECISION;
    """)
    _schema_ready = True


# --------------------------------------------------------------------------- #
# POST /memory/store
# --------------------------------------------------------------------------- #

@router.post("/memory/store")
async def store_memory(request: Request, conn=Depends(_get_conn)):
    """Persist a CRS reasoning step with optional embedding + spectral metadata."""
    await _ensure_schema(conn)
    body = await request.json()

    key = body.get("step_id", str(uuid.uuid4()))
    value = body.get("text", json.dumps(body, default=str))
    category = body.get("category", "reasoning")
    embedding: list[float] | None = body.get("embedding")
    spectral: dict[str, Any] = body.get("spectral", {})
    r_ratio = spectral.get("r_ratio")
    shi = spectral.get("shi")

    # Ensure the CRS namespace row exists
    await conn.execute(
        """
        INSERT INTO namespaces (id, owner, name, tier, created_at)
        VALUES ($1, 'crs', 'CRS Personal', 'personal', NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        CRS_NAMESPACE,
    )

    row = await conn.fetchrow(
        """
        INSERT INTO memories
            (namespace_id, key, value, category, source, crs_embedding, r_ratio, shi, content_hash)
        VALUES ($1, $2, $3, $4, 'crs', $5, $6, $7, '')
        ON CONFLICT (namespace_id, key) DO UPDATE SET
            value         = EXCLUDED.value,
            crs_embedding = EXCLUDED.crs_embedding,
            r_ratio       = EXCLUDED.r_ratio,
            shi           = EXCLUDED.shi,
            version       = memories.version + 1,
            last_updated  = NOW()
        RETURNING id, key, version
        """,
        CRS_NAMESPACE,
        key,
        value,
        category,
        np.array(embedding, dtype=np.float32) if embedding else None,
        r_ratio,
        shi,
    )

    return {
        "id": str(row["id"]),
        "key": row["key"],
        "version": row["version"],
        "receipt": {"id": str(row["id"])},
    }


# --------------------------------------------------------------------------- #
# POST /memory/geometric-search
# --------------------------------------------------------------------------- #

@router.post("/memory/geometric-search")
async def geometric_search(request: Request, conn=Depends(_get_conn)):
    """Search CRS memories by spectral range or embedding similarity."""
    await _ensure_schema(conn)
    if not _schema_ready:
        return []  # memories table doesn't exist yet
    body = await request.json()

    top_k = body.get("top_k", 10)

    # Mode 1: spectral range search (used by self-healing loop)
    if "r_min" in body:
        r_min = body["r_min"]
        r_max = body.get("r_max", 1.0)
        shi_min = body.get("shi_min", 0.0)

        rows = await conn.fetch(
            """
            SELECT id, key, value, category, crs_embedding, r_ratio, shi, last_updated
            FROM memories
            WHERE namespace_id = $1
              AND r_ratio >= $2 AND r_ratio <= $3
              AND shi >= $4
              AND is_deleted = FALSE
              AND crs_embedding IS NOT NULL
            ORDER BY last_updated DESC
            LIMIT $5
            """,
            CRS_NAMESPACE,
            r_min,
            r_max,
            shi_min,
            top_k,
        )
    # Mode 2: embedding similarity search (cosine distance via pgvector)
    elif "embedding" in body:
        embedding = body["embedding"]
        rows = await conn.fetch(
            """
            SELECT id, key, value, category, crs_embedding, r_ratio, shi, last_updated
            FROM memories
            WHERE namespace_id = $1
              AND is_deleted = FALSE
              AND crs_embedding IS NOT NULL
            ORDER BY crs_embedding <=> $2
            LIMIT $3
            """,
            CRS_NAMESPACE,
            np.array(embedding, dtype=np.float32),
            top_k,
        )
    else:
        return JSONResponse(
            status_code=400,
            content={"error": "Provide either spectral range (r_min/r_max/shi_min) or embedding"},
        )

    results: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {
            "id": str(row["id"]),
            "key": row["key"],
            "value": row["value"],
            "category": row["category"],
            "r_ratio": row["r_ratio"],
            "shi": row["shi"],
            "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
        }
        # Return embedding as a Python list for CRS consumption
        emb = row["crs_embedding"]
        if emb is not None:
            entry["embedding"] = list(emb) if hasattr(emb, "__iter__") else emb
        results.append(entry)

    return results


# --------------------------------------------------------------------------- #
# GET /memory/recent
# --------------------------------------------------------------------------- #

@router.get("/memory/recent")
async def recent_memories(request: Request, limit: int = 100, conn=Depends(_get_conn)):
    """Return the most recently stored CRS memories."""
    await _ensure_schema(conn)
    if not _schema_ready:
        return []
    rows = await conn.fetch(
        """
        SELECT id, key, value, category, crs_embedding, r_ratio, shi, last_updated
        FROM memories
        WHERE namespace_id = $1 AND is_deleted = FALSE
        ORDER BY last_updated DESC
        LIMIT $2
        """,
        CRS_NAMESPACE,
        limit,
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        entry: dict[str, Any] = {
            "id": str(row["id"]),
            "key": row["key"],
            "value": row["value"],
            "category": row["category"],
            "r_ratio": row["r_ratio"],
            "shi": row["shi"],
            "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
        }
        emb = row["crs_embedding"]
        if emb is not None:
            entry["embedding"] = list(emb) if hasattr(emb, "__iter__") else emb
        results.append(entry)

    return results


# --------------------------------------------------------------------------- #
# GET /memory/{memory_id}/receipt
# --------------------------------------------------------------------------- #

@router.get("/memory/{memory_id}/receipt")
async def get_receipt(memory_id: str, conn=Depends(_get_conn)):
    """Return an integrity receipt for a stored memory."""
    row = await conn.fetchrow(
        """
        SELECT id, key, content_hash, version, last_updated
        FROM memories
        WHERE id = $1 AND namespace_id = $2 AND is_deleted = FALSE
        """,
        memory_id,
        CRS_NAMESPACE,
    )
    if not row:
        return JSONResponse(status_code=404, content={"error": "memory not found"})

    return {
        "id": str(row["id"]),
        "key": row["key"],
        "content_hash": row["content_hash"],
        "version": row["version"],
        "verified_at": row["last_updated"].isoformat() if row["last_updated"] else None,
    }
