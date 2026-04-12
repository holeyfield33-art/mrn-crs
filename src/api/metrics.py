"""Prometheus metrics configuration."""

from __future__ import annotations

from prometheus_client import Counter

# Custom application metrics
crs_requests_total = Counter(
    "crs_requests_total",
    "Total CRS requests",
    ["endpoint", "status", "client"],
)

crs_self_heal_total = Counter(
    "crs_self_heal_total",
    "Total self-healing actions",
    ["outcome"],
)
