#!/usr/bin/env python3
"""Reject active legacy edge-hosting deployment artifacts.

The supported deployment path is Netlify (website), Render (API) and Supabase
(archive).  Historical validation evidence and the decommission runbook are
intentionally exempt because they are records, not deployment configuration.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_TOKEN = re.compile(r"\b(?:cloudflare|wrangler|vinext|workerd)\b", re.IGNORECASE)
BLOCKED_PATHS = (
    re.compile(r"(^|/)\.cloudflare/", re.IGNORECASE),
    re.compile(r"(^|/)\.wrangler/", re.IGNORECASE),
    re.compile(r"(^|/)wrangler\.(?:toml|json|jsonc)$", re.IGNORECASE),
    re.compile(r"(^|/)cloudflare\.config\.[^/]+$", re.IGNORECASE),
    re.compile(r"(^|/)runtime-cloudflare\.[^/]+$", re.IGNORECASE),
    re.compile(r"(^|/)worker-configuration\.d\.ts$", re.IGNORECASE),
    re.compile(r"(^|/)_worker\.(?:js|ts|mjs)$", re.IGNORECASE),
    re.compile(r"^web/src/worker\.ts$", re.IGNORECASE),
    re.compile(r"^web/vite\.config\.(?:js|ts|mjs|cjs)$", re.IGNORECASE),
    re.compile(r"^web/tests/workers/", re.IGNORECASE),
    re.compile(r"^\.github/workflows/workers-checks\.ya?ml$", re.IGNORECASE),
)
HISTORICAL_FILES = {
    "docs/LEGACY_EDGE_DECOMMISSION.md",
    "docs/SPY_QQQ_VALIDATION_2026-10-27.md",
    "scripts/check_deployment_boundary.py",
    "tests/test_deployment_boundary.py",
}
HISTORICAL_DIRECTORIES = ("docs/validation/",)
CONTENT_SKIP = {"web/package-lock.json"}
MAX_CONTENT_BYTES = 2_000_000


def tracked_files(root: Path) -> list[str]:
    """Return tracked paths without depending on local untracked artifacts."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def is_historical(relative_path: str) -> bool:
    return relative_path in HISTORICAL_FILES or any(
        relative_path.startswith(prefix) for prefix in HISTORICAL_DIRECTORIES
    )


def scan(root: Path, files: list[str] | None = None) -> list[str]:
    """Return active deployment-boundary violations for the supplied paths."""
    if files is None:
        files = tracked_files(root)

    problems: list[str] = []
    for relative_path in sorted(set(files)):
        if is_historical(relative_path):
            continue
        if any(pattern.search(relative_path) for pattern in BLOCKED_PATHS):
            problems.append(f"{relative_path}: blocked legacy deployment path")
            continue
        if relative_path in CONTENT_SKIP:
            continue

        path = root / relative_path
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(f"{relative_path}: cannot read ({exc})")
            continue
        if len(raw) > MAX_CONTENT_BYTES or b"\0" in raw[:4096]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for match in ACTIVE_TOKEN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(
                f"{relative_path}:{line}: active legacy token {match.group(0)!r}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    try:
        files = tracked_files(args.root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"deployment boundary check failed: {exc}", file=sys.stderr)
        return 2

    problems = scan(args.root, files)
    if problems:
        print("Active legacy edge deployment artifacts are not allowed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"Deployment boundary check passed ({len(files)} tracked files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
