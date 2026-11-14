from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from html import unescape
from pathlib import Path
from typing import cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".github/scripts/image-scan-policy.py"
WORKFLOW = ROOT / ".github/workflows/images.yml"
DIGEST = "sha256:" + "a" * 64
SCANNER = (
    "ghcr.io/aquasecurity/trivy:0.76.2@sha256:"
    "8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"
)
ABSENT = object()


def package_result(result_class: str, kind: str) -> dict[str, object]:
    return {
        "Target": f"fixture ({kind})",
        "Class": result_class,
        "Type": kind,
        "Packages": [{"Name": "fixture-package", "Version": "1.0"}],
    }


@pytest.fixture
def report() -> dict[str, object]:
    return {
        "SchemaVersion": 2,
        "ArtifactType": "container_image",
        "Metadata": {"ImageID": DIGEST, "OS": {"Family": "debian", "Name": "13"}},
        "Results": [
            package_result("os-pkgs", "debian"),
            package_result("lang-pkgs", "python-pkg"),
        ],
    }


def finding(severity: str, fixed: object = ABSENT) -> dict[str, object]:
    vulnerability: dict[str, object] = {
        "VulnerabilityID": "CVE-2026-12345",
        "PkgName": "fixture-package",
        "InstalledVersion": "1.0",
        "Severity": severity,
    }
    if fixed is not ABSENT:
        vulnerability["FixedVersion"] = fixed
    return vulnerability


def modify(document: object, path: tuple[str | int, ...], value: object) -> None:
    current = document
    for key in path[:-1]:
        if isinstance(key, int):
            current = cast(list[object], current)[key]
        else:
            current = cast(dict[str, object], current)[key]
    final = path[-1]
    if isinstance(final, int):
        cast(list[object], current)[final] = value
    elif value is ABSENT:
        cast(dict[str, object], current).pop(final, None)
    else:
        cast(dict[str, object], current)[final] = value


def run_policy(
    tmp_path: Path,
    report: object,
    reviewed: object = ABSENT,
    *,
    config: str = DIGEST,
    image_id: str = DIGEST,
    expected_os: str = "debian",
    library: str = "python-pkg",
    raw_report: str | None = None,
    raw_blocklist: str | None = None,
    missing: str = "",
    artifact: str = "image-scan-fixture",
) -> tuple[subprocess.CompletedProcess[str], str]:
    report_path = tmp_path / "report.json"
    blocklist_path = tmp_path / "blocklist.json"
    summary_path = tmp_path / "summary.md"
    report_content = json.dumps(report) if raw_report is None else raw_report
    reviewed_content = json.dumps({} if reviewed is ABSENT else reviewed)
    blocklist_content = reviewed_content if raw_blocklist is None else raw_blocklist
    if missing != "report":
        report_path.write_text(report_content, encoding="utf-8")
    if missing != "blocklist":
        blocklist_path.write_text(blocklist_content, encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            str(POLICY),
            "evaluate",
            "--report",
            str(report_path),
            "--blocklist",
            str(blocklist_path),
            "--image-id",
            image_id,
            "--config-digest",
            config,
            "--expected-os",
            expected_os,
            "--expected-library",
            library,
            "--summary",
            str(summary_path),
            "--artifact-name",
            artifact,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if missing != "report":
        assert report_path.read_text(encoding="utf-8") == report_content
    if missing != "blocklist":
        assert blocklist_path.read_text(encoding="utf-8") == blocklist_content
    return process, summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("result_index", "severity", "fixed"),
    [
        (0, "HIGH", "2.0"),
        (0, "CRITICAL", ">= 2.0, < 3.0"),
        (1, "HIGH", "2.0, 3.1"),
        (1, "CRITICAL", "2.0"),
    ],
)
def test_fixable_severe_findings_block(
    tmp_path: Path,
    report: dict[str, object],
    result_index: int,
    severity: str,
    fixed: str,
) -> None:
    modify(
        report,
        ("Results", result_index, "Vulnerabilities"),
        [finding(severity, fixed)],
    )
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 1, process.stderr
    assert "Blocking findings: **1**" in summary
    assert "Unfixed HIGH/CRITICAL: **0**" in summary


@pytest.mark.parametrize(
    ("result_index", "severity", "fixed"),
    [
        (0, "HIGH", ABSENT),
        (0, "CRITICAL", ""),
        (1, "HIGH", ""),
        (1, "CRITICAL", ABSENT),
    ],
)
def test_unfixed_severe_findings_pass_with_residual_risk(
    tmp_path: Path,
    report: dict[str, object],
    result_index: int,
    severity: str,
    fixed: object,
) -> None:
    modify(
        report,
        ("Results", result_index, "Vulnerabilities"),
        [finding(severity, fixed)],
    )
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 0, process.stderr
    assert "Blocking findings: **0**" in summary
    assert "Unfixed HIGH/CRITICAL: **1**" in summary
    assert "residual risk" in summary
    assert "full raw report and metadata" in summary


@pytest.mark.parametrize(
    ("severity", "fixed"),
    [
        ("UNKNOWN", ABSENT),
        ("LOW", "2.0"),
        ("MEDIUM", ""),
        ("HIGH", ""),
        ("CRITICAL", "2.0"),
    ],
)
def test_reviewed_id_blocks_at_every_severity(
    tmp_path: Path,
    report: dict[str, object],
    severity: str,
    fixed: object,
) -> None:
    modify(report, ("Results", 1, "Vulnerabilities"), [finding(severity, fixed)])
    reviewed = {"CVE-2026-12345": "Fixture confirms an exposed package path."}
    process, summary = run_policy(tmp_path, report, reviewed)
    assert process.returncode == 1, process.stderr
    assert "Blocking findings: **1**" in summary


@pytest.mark.parametrize("severity", ["UNKNOWN", "LOW", "MEDIUM"])
def test_lower_severity_fixes_remain_in_raw_report(
    tmp_path: Path,
    report: dict[str, object],
    severity: str,
) -> None:
    modify(report, ("Results", 0, "Vulnerabilities"), [finding(severity, "2.0")])
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 0, process.stderr
    assert "Blocking findings: **0**" in summary


@pytest.mark.parametrize("vulnerabilities", [ABSENT, []])
@pytest.mark.parametrize("eosl", [ABSENT, False])
def test_clean_report_passes(
    tmp_path: Path,
    report: dict[str, object],
    vulnerabilities: object,
    eosl: object,
) -> None:
    modify(report, ("Results", 0, "Vulnerabilities"), vulnerabilities)
    modify(report, ("Metadata", "OS", "EOSL"), eosl)
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 0, process.stderr
    assert "Blocking findings: **0**" in summary


def test_alpine_without_expected_language_passes(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    modify(report, ("Metadata", "OS", "Family"), "alpine")
    report["Results"] = [package_result("os-pkgs", "alpine")]
    process, _ = run_policy(tmp_path, report, expected_os="alpine", library="")
    assert process.returncode == 0, process.stderr


def test_node_package_coverage_passes(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    modify(report, ("Results", 1, "Type"), "node-pkg")
    process, _ = run_policy(tmp_path, report, library="node-pkg")
    assert process.returncode == 0, process.stderr


def test_vulnerability_free_eol_report_fails_with_actionable_reason(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    modify(report, ("Metadata", "OS", "EOSL"), True)
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 2
    assert "image OS is end of life; update the base image" in summary
    assert "image OS is end of life" in process.stderr


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("SchemaVersion",), ABSENT),
        (("SchemaVersion",), "2"),
        (("SchemaVersion",), 2.0),
        (("ArtifactType",), "filesystem"),
        (("Metadata",), None),
        (("Metadata", "ImageID"), "sha256:" + "b" * 64),
        (("Metadata", "OS"), []),
        (("Metadata", "OS", "Family"), "alpine"),
        (("Metadata", "OS", "Family"), "unsupported"),
        (("Metadata", "OS", "Name"), "  "),
        (("Metadata", "OS", "EOSL"), "false"),
        (("Metadata", "OS", "EOSL"), None),
        (("Metadata", "OS", "EOSL"), 0),
        (("Results",), ABSENT),
        (("Results",), []),
        (("Results",), {}),
        (("Results", 0), None),
        (("Results", 0, "Target"), ""),
        (("Results", 0, "Class"), "config"),
        (("Results", 0, "Class"), "lang-pkgs"),
        (("Results", 0, "Type"), "alpine"),
        (("Results", 0, "Type"), "unsupported"),
        (("Results", 1, "Type"), "node-pkg"),
        (("Results", 0, "Packages"), ABSENT),
        (("Results", 0, "Packages"), []),
        (("Results", 1, "Packages"), None),
        (("Results", 1, "Packages"), [None]),
        (("Results", 0, "Packages", 0, "Name"), ABSENT),
        (("Results", 0, "Packages", 0, "Version"), " "),
        (("Results", 1, "Vulnerabilities"), None),
        (("Results", 1, "Vulnerabilities"), {}),
        (("Results", 1, "Vulnerabilities"), [None]),
    ],
)
def test_invalid_shape_or_coverage_fails(
    tmp_path: Path,
    report: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    modify(report, path, value)
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 2, process.stderr
    assert "validation failed" in summary


def test_missing_language_result_fails(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    report["Results"] = [package_result("os-pkgs", "debian")]
    process, _ = run_policy(tmp_path, report)
    assert process.returncode == 2


def test_additional_incomplete_result_fails(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    cast(list[object], report["Results"]).append(
        {"Target": "extra", "Class": "lang-pkgs", "Type": "node-pkg", "Packages": []}
    )
    process, _ = run_policy(tmp_path, report)
    assert process.returncode == 2


@pytest.mark.parametrize(
    "fixed", [None, False, 0, 1, [], {}, " ", "\t", "2.0\n", "2\x7f"]
)
def test_malformed_fixed_version_fails(
    tmp_path: Path,
    report: dict[str, object],
    fixed: object,
) -> None:
    modify(report, ("Results", 0, "Vulnerabilities"), [finding("HIGH", fixed)])
    process, _ = run_policy(tmp_path, report)
    assert process.returncode == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("VulnerabilityID", ABSENT),
        ("VulnerabilityID", " "),
        ("PkgName", None),
        ("InstalledVersion", ABSENT),
        ("InstalledVersion", ""),
        ("Severity", "high"),
        ("Severity", "UNRECOGNIZED"),
        ("Severity", None),
        ("PkgName", "package\n::warning::injected"),
    ],
)
def test_malformed_vulnerability_fails(
    tmp_path: Path,
    report: dict[str, object],
    key: str,
    value: object,
) -> None:
    vulnerability = finding("HIGH")
    modify(vulnerability, (key,), value)
    modify(report, ("Results", 1, "Vulnerabilities"), [vulnerability])
    process, _ = run_policy(tmp_path, report)
    assert process.returncode == 2


@pytest.mark.parametrize("invalid", ["", "{", "null", "[]", "{} {}", "NaN"])
def test_missing_or_malformed_report_fails(
    tmp_path: Path,
    report: dict[str, object],
    invalid: str,
) -> None:
    process, _ = run_policy(tmp_path, report, raw_report=invalid)
    assert process.returncode == 2


def test_duplicate_report_key_fails(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    raw = json.dumps(report).replace(
        '"SchemaVersion": 2', '"SchemaVersion": 1, "SchemaVersion": 2'
    )
    process, _ = run_policy(tmp_path, report, raw_report=raw)
    assert process.returncode == 2


@pytest.mark.parametrize("missing", ["report", "blocklist"])
def test_missing_input_fails(
    tmp_path: Path,
    report: dict[str, object],
    missing: str,
) -> None:
    process, _ = run_policy(tmp_path, report, missing=missing)
    assert process.returncode == 2


@pytest.mark.parametrize(
    "reviewed",
    [
        None,
        [],
        {"CVE-2026-12345": ""},
        {"ID": " "},
        {"ID": None},
        {"ID": 1},
        {"ID": "Reason\n::warning::injected"},
        {" ": "Reason"},
    ],
)
def test_invalid_blocklist_fails(
    tmp_path: Path,
    report: dict[str, object],
    reviewed: object,
) -> None:
    process, _ = run_policy(tmp_path, report, reviewed)
    assert process.returncode == 2


@pytest.mark.parametrize("invalid", ["", "{", '{"ID":"one","ID":"two"}'])
def test_malformed_blocklist_fails(
    tmp_path: Path,
    report: dict[str, object],
    invalid: str,
) -> None:
    process, _ = run_policy(tmp_path, report, raw_blocklist=invalid)
    assert process.returncode == 2


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("config", "md5:" + "a" * 32),
        ("config", "sha256:abc"),
        ("image_id", ""),
        ("image_id", "a" * 64),
    ],
)
def test_identity_requires_sha256(
    tmp_path: Path,
    report: dict[str, object],
    invalid: str,
    field: str,
) -> None:
    process, _ = run_policy(tmp_path, report, **{field: invalid})
    assert process.returncode == 2


def test_summary_escapes_untrusted_values(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    payload = "</code><img src=x>|[click](https://example.test)::warning::"
    vulnerability = finding("HIGH", payload)
    for key in ("VulnerabilityID", "PkgName", "InstalledVersion"):
        vulnerability[key] = payload
    modify(report, ("Results", 0, "Target"), payload)
    modify(report, ("Results", 0, "Vulnerabilities"), [vulnerability])
    process, summary = run_policy(
        tmp_path, report, {payload: payload}, artifact=payload + "\n## injected"
    )
    assert process.returncode == 1
    assert payload not in summary
    for unsafe in ("<img", "[click]", "::warning::", "\n## injected"):
        assert unsafe not in summary
        assert unsafe not in process.stdout + process.stderr
    assert "&#60;" in summary
    rows = [line for line in summary.splitlines() if line.startswith("| ")]
    assert len(rows) == 3
    assert all(line.count("|") == 7 for line in rows)


def test_summary_limits_rows_and_field_lengths(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    vulnerabilities = [finding("HIGH", "x" * 10000) for _ in range(100)]
    modify(report, ("Results", 0, "Vulnerabilities"), vulnerabilities)
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 1
    assert "Blocking findings: **100**" in summary
    assert "Showing 40 of 100" in summary
    assert len(summary) < 300000
    assert "x" * 1000 not in summary


def test_blocking_duplicates_precede_unfixed_rows(
    tmp_path: Path,
    report: dict[str, object],
) -> None:
    modify(
        report, ("Results", 0, "Vulnerabilities"), [finding("HIGH") for _ in range(40)]
    )
    later = package_result("lang-pkgs", "python-pkg")
    later["Target"] = "/app/later/requirements.txt"
    another_version = finding("CRITICAL", "3.0")
    another_version["InstalledVersion"] = "1.1"
    later["Vulnerabilities"] = [finding("HIGH", "2.0"), another_version]
    cast(list[object], report["Results"]).append(later)
    process, summary = run_policy(tmp_path, report)
    assert process.returncode == 1
    assert "Blocking findings: **2**" in summary
    assert "Unfixed HIGH/CRITICAL: **40**" in summary
    assert "Showing 40 of 42" in summary
    rows = [unescape(line) for line in summary.splitlines() if line.startswith("| ")]
    for row, version in zip(rows[2:4], ("1.0", "1.1"), strict=True):
        assert "CVE-2026-12345" in row
        assert "/app/later/requirements.txt / fixture-package" in row
        assert f"<code>{version}</code>" in row
        assert "Block: fix available" in row
    assert "Triage: no fix available" in rows[4]


def run_metadata(
    tmp_path: Path,
    database: object,
    scanner: str = SCANNER,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    database_path = tmp_path / "db.json"
    output = tmp_path / "metadata.json"
    database_path.write_text(json.dumps(database), encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            str(POLICY),
            "metadata",
            "--db-metadata",
            str(database_path),
            "--scanner-image",
            scanner,
            "--image-id",
            DIGEST,
            "--config-digest",
            DIGEST,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return process, output


def test_metadata_records_collection_identity_and_database(tmp_path: Path) -> None:
    database = {
        "Version": 2,
        "UpdatedAt": "2026-11-13T00:00:00Z",
        "NextUpdate": "2026-11-13T06:00:00Z",
    }
    process, output = run_metadata(tmp_path, database)
    assert process.returncode == 0, process.stderr
    assert json.loads(output.read_text()) == {
        "image_id": DIGEST,
        "config_digest": DIGEST,
        "scanner_image": SCANNER,
        "scanner_version": "0.76.2",
        "database": {key: database[key] for key in ("UpdatedAt", "NextUpdate")},
    }


@pytest.mark.parametrize(
    "database",
    [
        None,
        {},
        {"Version": 1, "UpdatedAt": "updated", "NextUpdate": "next"},
        {"Version": 2, "UpdatedAt": " ", "NextUpdate": "next"},
        {"Version": 2, "UpdatedAt": "updated", "NextUpdate": None},
    ],
)
def test_invalid_database_metadata_fails(tmp_path: Path, database: object) -> None:
    process, output = run_metadata(tmp_path, database)
    assert process.returncode == 2
    assert not output.exists()


def test_unpinned_scanner_metadata_fails(tmp_path: Path) -> None:
    database = {"Version": 2, "UpdatedAt": "updated", "NextUpdate": "next"}
    process, output = run_metadata(tmp_path, database, scanner="trivy:latest")
    assert process.returncode == 2
    assert not output.exists()


def workflow_step(name: str) -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    return source.split(f"      - name: {name}\n", 1)[1].split("      - name: ", 1)[0]


def test_workflow_matrix_matches_build_contracts() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    matrix = workflow["jobs"]["scan"]["strategy"]["matrix"]["include"]
    keys = ("name", "context", "dockerfile", "target", "os", "library")
    fields = [tuple(row[key] for key in keys) for row in matrix]
    assert fields == [
        (
            "backend-runtime",
            ".",
            "backend/Dockerfile",
            "runtime",
            "debian",
            "python-pkg",
        ),
        (
            "frontend-toolchain",
            "frontend",
            "frontend/Dockerfile",
            "toolchain",
            "debian",
            "node-pkg",
        ),
        (
            "frontend-build",
            "frontend",
            "frontend/Dockerfile",
            "build",
            "debian",
            "node-pkg",
        ),
        (
            "frontend-runtime",
            "frontend",
            "frontend/Dockerfile",
            "runtime",
            "alpine",
            "",
        ),
    ]


def test_workflow_keeps_full_scan_and_failure_propagation() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    scan = workflow_step("Scan an archive of the recorded image ID")
    database = workflow_step("Download and validate the vulnerability database")
    assert source.startswith(
        "name: Image security\n\non:\n  pull_request:\n  push:\n"
        "    branches: [main]\n  workflow_dispatch:\n"
    )
    assert "permissions:\n  contents: read\n" in source
    assert source.count("permissions:") == 1
    assert SCANNER in source
    for step in (scan, database):
        assert "set -euo pipefail" in step
        assert '--user "$(id -u):$(id -g)"' in step
        assert "--read-only --cap-drop ALL" in step
        assert "--security-opt no-new-privileges" in step
        assert "--tmpfs /tmp:rw,nosuid,nodev,size=512m" in step
    assert "--pkg-types os,library" in scan
    assert "--list-all-pkgs" in scan
    assert "--ignore-unfixed=false --ignorefile /dev/null --exit-code 0" in scan
    assert "--exit-on-eol 0 --format json --output /reports/report.json" in scan
    assert "--severity" not in scan
    assert "--skip-db-update" in scan
    assert 'test -s "$RUNNER_TEMP/trivy-reports/report.json"' in scan
    assert "continue-on-error" not in source
    assert "|| true" not in source
    assert "--exit-on-eol 1" not in source
    assert len(re.findall(r"^\s+if:", source, re.MULTILINE)) == 1


@pytest.mark.parametrize("scanner_exit", [0, 23])
def test_scan_step_propagates_scanner_exit_with_partial_report(
    tmp_path: Path, scanner_exit: int
) -> None:
    executables: dict[str, str] = {}
    for command in ("bash", "jq", "sha256sum", "tar", "cp", "id", "mktemp", "rm"):
        executable = shutil.which(command)
        if executable is None:
            pytest.skip(f"Install {command} on PATH to run the scan step fixture")
        executables[command] = str(Path(executable).absolute())
    subprocess_path = os.pathsep.join(
        dict.fromkeys(
            str(Path(executable).parent) for executable in executables.values()
        )
    )
    config = b"{}"
    config_hex = hashlib.sha256(config).hexdigest()
    archive_path = tmp_path / "fixture.tar"
    entries = {
        "manifest.json": json.dumps([{"Config": f"{config_hex}.json"}]).encode(),
        f"{config_hex}.json": config,
    }
    with tarfile.open(archive_path, "w") as archive:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    reports = tmp_path / "trivy-reports"
    reports.mkdir()
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    script = next(
        step["run"]
        for step in workflow["jobs"]["scan"]["steps"]
        if step["name"] == "Scan an archive of the recorded image ID"
    )
    docker_stub = """
docker() {
  case "$1" in
    save) cp "$STUB_ARCHIVE" "$3" ;;
    run)
      printf '%s\\n' '{"partial":true}' > "$RUNNER_TEMP/trivy-reports/report.json"
      return "$STUB_EXIT"
      ;;
    *) return 99 ;;
  esac
}
"""
    process = subprocess.run(
        [
            executables["bash"],
            "-c",
            docker_stub + script + "\nprintf 'scan completed\\n'\n",
        ],
        env={
            "PATH": subprocess_path,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            "IMAGE_ID": DIGEST,
            "TRIVY_IMAGE": SCANNER,
            "STUB_ARCHIVE": str(archive_path),
            "STUB_EXIT": str(scanner_exit),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (reports / "report.json").read_text() == '{"partial":true}\n'
    assert process.returncode == scanner_exit, process.stderr
    assert ("scan completed" in process.stdout) == (scanner_exit == 0)


def test_workflow_keeps_credential_probe_and_archive_identity() -> None:
    probe = workflow_step("Probe credential exclusions in the build context")
    for pattern in (
        'context / f"context-probe-{token}" / "nested"',
        '".env", ".env0600", f".env.{token}"',
        '".aws/credentials", ".ssh/id_rsa"',
        '".netrc", ".git-credentials", ".npmrc"',
        'f"{token}.key", f"private-{token}.pem", f"{token}.pem"',
        "path.chmod(0o600)",
        "Credential sentinel path leaked",
        "Credential sentinel content leaked",
        "Probe artifact cleanup failed",
        "finally:",
    ):
        assert pattern in probe
    build = workflow_step("Build and record the image ID")
    assert '--iidfile "$RUNNER_TEMP/image.iid" "$BUILD_CONTEXT"' in build
    assert '[[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]' in build
    scan = workflow_step("Scan an archive of the recorded image ID")
    for fragment in (
        'docker save --output "$image_archive" "$IMAGE_ID"',
        'tar -xOf "$image_archive" manifest.json',
        'type == "array" and length == 1',
        '[[ "$config_hex" =~ ^[0-9a-f]{64}$ ]]',
        'tar -xOf "$image_archive" "$config_path" | sha256sum',
        '[[ "${config_checksum%% *}" == "$config_hex" ]]',
        'config_digest="sha256:$config_hex"',
        'dst=/image.tar,readonly"',
        "--input /image.tar",
    ):
        assert fragment in scan


def test_workflow_uploads_raw_evidence_after_policy_failure() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    metadata = workflow_step("Record scan metadata")
    policy = workflow_step("Enforce image scan policy and coverage")
    upload = workflow_step("Upload image scan evidence")
    assert source.index("Record scan metadata") < source.index(
        "Enforce image scan policy"
    )
    assert source.index("Enforce image scan policy") < source.index(
        "Upload image scan evidence"
    )
    assert "python3 .github/scripts/image-scan-policy.py metadata" in metadata
    assert '--db-metadata "$RUNNER_TEMP/trivy-cache/db/metadata.json"' in metadata
    assert '--scanner-image "$TRIVY_IMAGE"' in metadata
    assert '--output "$RUNNER_TEMP/trivy-reports/metadata.json"' in metadata
    assert "python3 .github/scripts/image-scan-policy.py evaluate" in policy
    assert '--report "$RUNNER_TEMP/trivy-reports/report.json"' in policy
    assert "--blocklist .github/image-scan-blocklist.json" in policy
    assert '--image-id "$IMAGE_ID" --config-digest "$CONFIG_DIGEST"' in policy
    assert (
        '--expected-os "$EXPECTED_OS" --expected-library "$EXPECTED_LIBRARY"' in policy
    )
    assert '--summary "$GITHUB_STEP_SUMMARY" --artifact-name "$ARTIFACT_NAME"' in policy
    assert "ARTIFACT_NAME: image-scan-${{ matrix.name }}" in policy
    assert "if: ${{ always() && steps.scan.outcome == 'success' }}" in upload
    assert (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2"
        in upload
    )
    assert "name: image-scan-${{ matrix.name }}" in upload
    assert "${{ runner.temp }}/trivy-reports/report.json" in upload
    assert "${{ runner.temp }}/trivy-reports/metadata.json" in upload
    assert "if-no-files-found: error" in upload


def test_checked_in_blocklist_is_reviewed_mapping() -> None:
    reviewed = json.loads((ROOT / ".github/image-scan-blocklist.json").read_text())
    assert isinstance(reviewed, dict)
    for identifier, reason in reviewed.items():
        assert isinstance(identifier, str)
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", identifier)
        assert isinstance(reason, str) and reason.strip() and reason.isprintable()
