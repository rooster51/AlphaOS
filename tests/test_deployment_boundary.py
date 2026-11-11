"""The deployment guard must reject active edge-hosting artifacts, not evidence."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = spec_from_file_location(
    "check_deployment_boundary",
    ROOT / "scripts/check_deployment_boundary.py",
)
assert SPEC and SPEC.loader
boundary = module_from_spec(SPEC)
SPEC.loader.exec_module(boundary)


def write(root: Path, relative_path: str, content: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_current_tree_has_no_active_legacy_deployment_artifacts():
    files = boundary.tracked_files(ROOT)
    assert files
    assert boundary.scan(ROOT, files) == []


@pytest.mark.parametrize(
    "relative_path",
    [
        "wrangler.toml",
        "web/cloudflare.config.ts",
        "web/src/lib/runtime-cloudflare.ts",
        "web/src/worker.ts",
        "web/vite.config.ts",
        "web/tests/workers/runtime.test.mjs",
        ".github/workflows/workers-checks.yml",
    ],
)
def test_blocks_legacy_deployment_paths(tmp_path, relative_path):
    write(tmp_path, relative_path)
    assert any(relative_path in problem for problem in boundary.scan(tmp_path, [relative_path]))


@pytest.mark.parametrize(
    "relative_path,content",
    [
        (".github/workflows/deploy.yml", "run: npx wrangler deploy\n"),
        ("web/package.json", '{"devDependencies":{"vinext":"^0.1.0"}}\n'),
        ("web/src/config.ts", "export const runtime = 'cloudflare';\n"),
    ],
)
def test_blocks_active_legacy_tokens(tmp_path, relative_path, content):
    write(tmp_path, relative_path, content)
    problems = boundary.scan(tmp_path, [relative_path])
    assert any("active legacy token" in problem for problem in problems)


def test_allows_historical_evidence_and_decommission_documentation(tmp_path):
    files = [
        "docs/validation/spy-qqq-2026-10-27.json",
        "docs/SPY_QQQ_VALIDATION_2026-10-27.md",
        "docs/LEGACY_EDGE_DECOMMISSION.md",
    ]
    write(tmp_path, files[0], '{"runtime": "cloudflare"}\n')
    write(tmp_path, files[1], "The retired Worker preview is historical.\n")
    write(tmp_path, files[2], "Remove the Cloudflare Workers and Pages app; revoke wrangler access.\n")
    assert boundary.scan(tmp_path, files) == []
