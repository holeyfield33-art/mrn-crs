"""Prometheus metrics configuration."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

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

crs_client_call_duration_seconds = Histogram(
    "crs_client_call_duration_seconds",
    "Duration of calls to downstream services",
    ["service"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
