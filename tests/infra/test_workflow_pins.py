import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))

USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(?P<value>.*?)\s*$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d[\w.]*$")

NEW_IGNORE_LINES = [
    ".env.*",
    "!.env.example",
    "*.pem",
    "!infra/rds/us-east-1-bundle.pem",
    "*.key",
    "cdk.out/",
    "cdk.context.json",
]


def test_workflows_exist() -> None:
    assert WORKFLOWS


def test_every_uses_value_is_pinned() -> None:
    bad = []
    for path in WORKFLOWS:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            match = USES_LINE.match(line)
            if not match:
                continue
            value = match.group("value")
            if value.startswith("docker://"):
                ok = "@sha256:" in value
            else:
                ok = PINNED.match(value) is not None
            if not ok:
                bad.append(f"{path.name}:{number}: {value}")
    assert not bad, bad


def test_pip_audit_is_pinned() -> None:
    bad = []
    for path in WORKFLOWS:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"uvx pip-audit(?!==)", line):
                bad.append(f"{path.name}:{number}: {line.strip()}")
    assert not bad, bad


def test_every_workflow_sets_concurrency() -> None:
    bad = []
    for path in WORKFLOWS:
        data = yaml.safe_load(path.read_text())
        concurrency = data.get("concurrency")
        if concurrency != {
            "group": "${{ github.workflow }}-${{ github.ref }}",
            "cancel-in-progress": "${{ github.event_name == 'pull_request' }}",
        }:
            bad.append(f"{path.name}: {concurrency}")
    assert not bad, bad


def test_gitignore_holds_secret_patterns() -> None:
    lines = (ROOT / ".gitignore").read_text().splitlines()
    missing = [line for line in NEW_IGNORE_LINES if line not in lines]
    assert not missing, missing
