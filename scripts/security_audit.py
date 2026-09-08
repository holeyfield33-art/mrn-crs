#!/usr/bin/env python3
"""Static security audit for MRN-CRS environment configuration.

Scans a .env (or .env.example) file for the kind of misconfigurations that
turn "works on my machine" into an incident: placeholder secrets left in
place, auth disabled by default, and autonomous-mode combinations that
remove every safety gate at once.

Usage:
    python scripts/security_audit.py [path/to/.env]

Exits non-zero if any HIGH severity finding is present, so it can gate CI.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Secrets that ship as examples and must never reach a real deployment.
_KNOWN_PLACEHOLDER_VALUES = {
    "password",
    "changeme",
    "changeme_aletheia_secret_minimum32chars",
    "crs-dev-key",
    "crs-dev-jwt-secret-minimum32chars",
    "re_placeholder",
    "sk_test_placeholder",
    "deepseek_v4",
}

# Substrings that mark a value as an obvious placeholder even if the exact
# string above isn't matched (e.g. a user renamed it slightly).
_PLACEHOLDER_MARKERS = ("changeme", "placeholder", "dev-key", "dev-jwt", "example", "test_placeholder")

# Secrets whose length matters (HMAC / JWT signing keys).
_MIN_SECRET_LENGTH = {
    "ALETHEIA_RECEIPT_SECRET": 32,
    "JWT_SECRET": 32,
}


@dataclass
class Finding:
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    key: str
    message: str


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _is_placeholder(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered in _KNOWN_PLACEHOLDER_VALUES:
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def audit(values: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []

    # 1. Auth disabled entirely.
    if not values.get("CRS_API_KEYS", "").strip():
        findings.append(Finding(
            "HIGH", "CRS_API_KEYS",
            "Empty – API authentication is disabled, every endpoint (including /reason) is open.",
        ))

    # 2. Placeholder / default secrets still in place.
    for key, value in values.items():
        if _is_placeholder(value):
            findings.append(Finding(
                "HIGH", key,
                f"Looks like an unchanged example value ({value!r}) – rotate before deploying.",
            ))

    # 3. Signing secrets that are too short to be a real HMAC/JWT key.
    for key, min_len in _MIN_SECRET_LENGTH.items():
        value = values.get(key, "")
        if value and not _is_placeholder(value) and len(value) < min_len:
            findings.append(Finding(
                "MEDIUM", key,
                f"Only {len(value)} chars – recommend >= {min_len} for a signing secret.",
            ))

    # 4. Autonomous mode + no human gates + no auth = fully unsupervised and open.
    autonomous = values.get("AUTONOMOUS_MODE", "false").strip().lower() == "true"
    human_gates_off = values.get("ENABLE_HUMAN_GATES", "true").strip().lower() == "false"
    auth_off = not values.get("CRS_API_KEYS", "").strip()
    if autonomous and human_gates_off and auth_off:
        findings.append(Finding(
            "HIGH", "AUTONOMOUS_MODE",
            "Autonomous mode + human gates disabled + no API auth: policy denials are overridden, "
            "escalations are skipped, and anyone can call /reason. Restrict at least one of these "
            "before running unattended.",
        ))
    elif autonomous and human_gates_off:
        findings.append(Finding(
            "MEDIUM", "AUTONOMOUS_MODE",
            "Autonomous mode is on and human gates are off – policy denials and health-check "
            "escalations are both bypassed. Confirm this is intentional for this environment.",
        ))

    # 5. Freeze safety net turned off.
    if values.get("FREEZE_ON_CRITICAL", "true").strip().lower() == "false":
        findings.append(Finding(
            "MEDIUM", "FREEZE_ON_CRITICAL",
            "Critical entropy-collapse freeze is disabled – the self-healing loop can no longer "
            "halt a runaway agent.",
        ))

    # 6. Postgres password re-used as a well-known default.
    pg_pw = values.get("POSTGRES_PASSWORD", "")
    if pg_pw and re.fullmatch(r"password\d*", pg_pw, flags=re.IGNORECASE):
        findings.append(Finding(
            "HIGH", "POSTGRES_PASSWORD",
            "Default/trivial Postgres password – guessable by any bot scanning exposed ports.",
        ))

    return findings


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else None
    if target is None:
        env_path = Path(".env")
        example_path = Path(".env.example")
        if env_path.exists():
            target = env_path
        elif example_path.exists():
            print("No .env found – auditing .env.example instead (template, not a live config).\n")
            target = example_path
        else:
            print("No .env or .env.example found.", file=sys.stderr)
            return 2

    if not target.exists():
        print(f"File not found: {target}", file=sys.stderr)
        return 2

    values = parse_env(target)
    findings = audit(values)

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings.sort(key=lambda f: order[f.severity])

    print(f"Security audit: {target}")
    print(f"{len(values)} variables checked, {len(findings)} finding(s)\n")

    if not findings:
        print("No issues found.")
        return 0

    for f in findings:
        print(f"  [{f.severity:6}] {f.key}: {f.message}")

    high_count = sum(1 for f in findings if f.severity == "HIGH")
    print(f"\n{high_count} HIGH severity finding(s).")
    return 1 if high_count else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
