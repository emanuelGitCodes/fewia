from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import cast

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SCANNER = re.compile(r"ghcr\.io/aquasecurity/trivy:([0-9.]+)@sha256:[0-9a-f]{64}\Z")
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SUMMARY_LIMIT = 40


class PolicyError(ValueError):
    pass


class EndOfLifeError(PolicyError):
    pass


def mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PolicyError(f"{label} MUST be an object")
    return cast(dict[str, object], value)


def array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise PolicyError(f"{label} MUST be an array")
    return cast(list[object], value)


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{label} MUST be a nonblank string")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for char in value
    ):
        raise PolicyError(f"{label} MUST NOT contain controls")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("JSON MUST NOT contain duplicate keys")
        result[key] = value
    return result


def reject_constant(value: str) -> object:
    raise PolicyError("JSON MUST NOT contain nonfinite numbers")


def load(path: Path) -> object:
    return cast(
        object,
        json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        ),
    )


def digest(value: str, label: str) -> str:
    if not DIGEST.fullmatch(value):
        raise PolicyError(f"{label} MUST be a SHA-256 digest")
    return value


def blocklist(path: Path) -> dict[str, str]:
    entries = mapping(load(path), "Blocklist")
    return {
        text(identifier, "Blocklist ID"): text(reason, "Blocklist reason")
        for identifier, reason in entries.items()
    }


@dataclass(frozen=True)
class Finding:
    target: str
    identifier: str
    package: str
    installed: str
    severity: str
    fixed: str
    reason: str

    @property
    def unfixed_severe(self) -> bool:
        return self.severity in {"HIGH", "CRITICAL"} and not self.fixed

    @property
    def blocking(self) -> bool:
        return bool(self.reason) or (
            self.severity in {"HIGH", "CRITICAL"} and bool(self.fixed)
        )


def evaluate(
    report: object,
    reviewed: dict[str, str],
    image_id: str,
    config_digest: str,
    expected_os: str,
    expected_library: str,
) -> list[Finding]:
    digest(image_id, "Build image ID")
    digest(config_digest, "Archive config digest")
    document = mapping(report, "Report")
    if type(document.get("SchemaVersion")) is not int or document["SchemaVersion"] != 2:
        raise PolicyError("Report SchemaVersion MUST be 2")
    if document.get("ArtifactType") != "container_image":
        raise PolicyError("Report ArtifactType MUST be container_image")
    metadata = mapping(document.get("Metadata"), "Report Metadata")
    if metadata.get("ImageID") != config_digest:
        raise PolicyError("Report image ID MUST match the archive config digest")
    os_data = mapping(metadata.get("OS"), "Report OS")
    if os_data.get("Family") != expected_os:
        raise PolicyError("Report OS family MUST match the matrix")
    text(os_data.get("Name"), "Report OS name")
    if "EOSL" in os_data and type(os_data["EOSL"]) is not bool:
        raise PolicyError("Report EOSL MUST be a boolean")
    if os_data.get("EOSL", False):
        raise EndOfLifeError("Report OS MUST NOT be end of life")
    results = array(document.get("Results"), "Report Results")
    if not results:
        raise PolicyError("Report Results MUST NOT be empty")
    coverage: set[tuple[str, str]] = set()
    findings: list[Finding] = []
    for entry in results:
        result = mapping(entry, "Result")
        target = text(result.get("Target"), "Result target")
        result_class = text(result.get("Class"), "Result class")
        if result_class not in {"os-pkgs", "lang-pkgs"}:
            raise PolicyError("Result class MUST be os-pkgs or lang-pkgs")
        result_type = text(result.get("Type"), "Result type")
        coverage.add((result_class, result_type))
        packages = array(result.get("Packages"), "Result Packages")
        if not packages:
            raise PolicyError("Result Packages MUST NOT be empty")
        for item in packages:
            package = mapping(item, "Package")
            text(package.get("Name"), "Package name")
            text(package.get("Version"), "Package version")
        vulnerabilities = array(result.get("Vulnerabilities", []), "Vulnerabilities")
        for item in vulnerabilities:
            vulnerability = mapping(item, "Vulnerability")
            identifier = text(vulnerability.get("VulnerabilityID"), "Vulnerability ID")
            package_name = text(vulnerability.get("PkgName"), "Vulnerability package")
            installed = text(
                vulnerability.get("InstalledVersion"), "Vulnerability installed version"
            )
            severity = text(vulnerability.get("Severity"), "Vulnerability severity")
            if severity not in SEVERITIES:
                raise PolicyError("Vulnerability severity MUST be a Trivy severity")
            fixed_value = vulnerability.get("FixedVersion", "")
            fixed = "" if fixed_value == "" else text(fixed_value, "FixedVersion")
            findings.append(
                Finding(
                    target,
                    identifier,
                    package_name,
                    installed,
                    severity,
                    fixed,
                    reviewed.get(identifier, ""),
                )
            )
    if ("os-pkgs", expected_os) not in coverage:
        raise PolicyError("Report MUST cover the expected OS packages")
    if expected_library and ("lang-pkgs", expected_library) not in coverage:
        raise PolicyError("Report MUST cover the expected language packages")
    return findings


def escaped(value: str) -> str:
    shortened = value if len(value) <= 100 else value[:100] + "…"
    return "<code>" + "".join(f"&#{ord(char)};" for char in shortened) + "</code>"


def summary(findings: list[Finding], artifact: str, error: str = "") -> str:
    blocking = sum(finding.blocking for finding in findings)
    unfixed = sum(finding.unfixed_severe for finding in findings)
    lines = ["### Container image scan policy", ""]
    if error:
        lines.append(f"**FAIL: {error}.**")
    else:
        lines.append(
            f"Blocking findings: **{blocking}**. Unfixed HIGH/CRITICAL: **{unfixed}**."
        )
    lines.extend(
        [
            "",
            "Unfixed HIGH/CRITICAL findings remain a residual risk, "
            "even when CI passes.",
            f"Download artifact {escaped(artifact)} from this workflow run "
            "for the full raw report and metadata.",
        ]
    )
    selected = [item for item in findings if item.blocking]
    selected.extend(
        item for item in findings if item.unfixed_severe and not item.blocking
    )
    if selected:
        lines.extend(
            [
                "",
                "| ID | Target / package | Installed | Severity | Fix | Decision |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in selected[:SUMMARY_LIMIT]:
            decision = item.reason or (
                "Block: fix available" if item.blocking else "Triage: no fix available"
            )
            cells = (
                item.identifier,
                f"{item.target} / {item.package}",
                item.installed,
                item.severity,
                item.fixed or "No fix available",
                decision,
            )
            lines.append("| " + " | ".join(escaped(cell) for cell in cells) + " |")
        lines.extend(
            [
                "",
                f"Showing {min(len(selected), SUMMARY_LIMIT)} of {len(selected)} "
                "triage findings.",
            ]
        )
    return "\n".join(lines) + "\n"


def write_metadata(args: argparse.Namespace) -> None:
    database = mapping(load(args.db_metadata), "Database metadata")
    if type(database.get("Version")) is not int or database["Version"] != 2:
        raise PolicyError("Database schema version MUST be 2")
    scanner = SCANNER.fullmatch(args.scanner_image)
    if scanner is None:
        raise PolicyError("Scanner image MUST include a version and SHA-256 pin")
    record = {
        "image_id": digest(args.image_id, "Build image ID"),
        "config_digest": digest(args.config_digest, "Archive config digest"),
        "scanner_image": args.scanner_image,
        "scanner_version": scanner.group(1),
        "database": {
            "UpdatedAt": text(database.get("UpdatedAt"), "Database UpdatedAt"),
            "NextUpdate": text(database.get("NextUpdate"), "Database NextUpdate"),
        },
    }
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    policy = commands.add_parser("evaluate")
    policy.add_argument("--report", type=Path, required=True)
    policy.add_argument("--blocklist", type=Path, required=True)
    policy.add_argument("--expected-os", required=True)
    policy.add_argument("--expected-library", default="")
    policy.add_argument("--summary", type=Path, required=True)
    policy.add_argument("--artifact-name", required=True)
    metadata = commands.add_parser("metadata")
    metadata.add_argument("--db-metadata", type=Path, required=True)
    metadata.add_argument("--scanner-image", required=True)
    metadata.add_argument("--output", type=Path, required=True)
    for command in (policy, metadata):
        command.add_argument("--image-id", required=True)
        command.add_argument("--config-digest", required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        if args.command == "metadata":
            write_metadata(args)
            return 0
        findings = evaluate(
            load(args.report),
            blocklist(args.blocklist),
            args.image_id,
            args.config_digest,
            args.expected_os,
            args.expected_library,
        )
        with args.summary.open("a", encoding="utf-8") as output:
            output.write(summary(findings, args.artifact_name))
        blocked = any(finding.blocking for finding in findings)
        print("Image policy blocked findings" if blocked else "Image policy passed")
        return 1 if blocked else 0
    except (PolicyError, OSError, UnicodeError, json.JSONDecodeError) as error:
        reason = (
            "image OS is end of life; update the base image"
            if isinstance(error, EndOfLifeError)
            else "policy input or report validation failed"
        )
        print(f"Image policy failed: {reason}", file=sys.stderr)
        if args.command == "evaluate":
            with args.summary.open("a", encoding="utf-8") as output:
                output.write(summary([], args.artifact_name, error=reason))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
