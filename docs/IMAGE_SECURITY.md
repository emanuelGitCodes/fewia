# Container image security

The [Image security workflow](../.github/workflows/images.yml) runs on pull
requests, pushes to `main`, and manual dispatch. It builds these Docker targets:

| Image | Build context | Dockerfile | Target | OS | Language coverage |
| --- | --- | --- | --- | --- | --- |
| backend-runtime | `.` | `backend/Dockerfile` | `runtime` | Debian | Python |
| frontend-toolchain | `frontend` | `frontend/Dockerfile` | `toolchain` | Debian | Node |
| frontend-build | `frontend` | `frontend/Dockerfile` | `build` | Debian | Node |
| frontend-runtime | `frontend` | `frontend/Dockerfile` | `runtime` | Alpine | None expected |

The matrix OS identifies the detected family inside each image. It does not
identify the developer's operating system. Developers build and scan these
images with Docker from their usual operating system.

The workflow probes credential exclusions before each build. It scans an
archive saved from the recorded build image ID. It verifies the archive
config checksum. The report image ID MUST match that config digest.
Trivy uses a pinned image. Both scanner runs use the runner's UID and GID.

## CI policy

Trivy collects complete JSON for OS and language packages. The scan includes
every severity, unfixed findings, and package records. It uses an empty
ignore file. The collector uses `--exit-code 0` and `--exit-on-eol 0` to
retain reports with findings or an end-of-life OS. Unexpected scanner errors
fail collection. The evaluator rejects an end-of-life OS, even without
vulnerabilities.

The [policy evaluator](../.github/scripts/image-scan-policy.py) applies these
rules after collection:

| Finding | CI decision | Triage action |
| --- | --- | --- |
| HIGH or CRITICAL with a fix | Block | Update the affected package or base image in a separate change. |
| HIGH or CRITICAL without a fix | Pass unless explicitly blocked | Review exposure, track the advisory, and apply available mitigations. |
| UNKNOWN, LOW, or MEDIUM | Pass unless explicitly blocked | Review the full report and prioritize remediation. |
| Any reviewed blocklist ID | Block at every severity, with or without a fix | Resolve the documented exposure or review the blocklist entry. |

An absent or empty `FixedVersion` means no fix is available in the report.
A nonblank text value means a fix is available. The evaluator accepts version
ranges and multiple versions. It rejects wrong types, controls, and
whitespace-only values. It does not compare version numbers itself.

The evaluator rejects missing or malformed reports and blocklists. It also
rejects image identity mismatches, end-of-life OS records, and incomplete
package coverage. Each result MUST retain a nonempty package list. The report
MUST contain the expected OS result and the matrix's expected language result.
An omitted `EOSL` field means false. A present `EOSL` MUST be a boolean.

Passing CI can leave HIGH or CRITICAL findings without fixes. Those findings
remain a residual risk. Maintainers MUST review exposure and track remediation.
A reviewed block stops CI when that remaining risk is unacceptable.

## Reviewed blocks

[`.github/image-scan-blocklist.json`](../.github/image-scan-blocklist.json)
maps exact vulnerability IDs to reviewed, factual reasons. An empty object
means no IDs are explicitly blocked. Each entry blocks its ID across all
scanned images and package types.

To add a block:

1. Inspect the raw finding and its advisory. Confirm the affected package and exposure.
2. Obtain independent review of the ID and reason.
3. Add the exact report ID as a JSON key. Use a nonempty factual reason as its value.
4. Describe the affected path, impact, and advisory evidence in the reason or linked review record.
5. Run the focused policy tests and required gates before merging the entry.

Maintainers MUST NOT add unreviewed IDs or placeholder reasons. To remove a
block, submit a reviewed change with evidence that resolves its stated risk.
Removing a block does not allow a fixable HIGH or CRITICAL finding to pass.

## Reports and metadata

Open the GitHub Actions run and download `image-scan-<matrix-name>` from
Artifacts. For example, the backend artifact is `image-scan-backend-runtime`.
Each artifact contains:

- `report.json`: the unchanged Trivy JSON, including all findings and packages.
- `metadata.json`: the build image ID, archive config digest, scanner image pin
  and version, and database `UpdatedAt` and `NextUpdate` values.

The workflow creates metadata after successful collection and before policy
evaluation. It uploads evidence even when policy validation or a finding
blocks CI, including EOL reports. It uploads only after the scan step succeeds.
A fatal scanner or archive failure prevents upload, even with a partial report.
Inspect the failed step's log for collection failures.
Report and metadata files stay in `RUNNER_TEMP` until artifact upload.

The job summary counts blocking findings and unfixed severe findings. It
identifies up to 40 triage findings and limits displayed field lengths.
Blocking rows appear before unfixed rows. The evaluator checks each raw
finding, including repeated IDs and packages at different paths or versions.
Report and blocklist values use escaped text. They do not appear in evaluator
stdout or stderr. EOL failures show a fixed reason to update the base image.
Download the artifact for all findings, complete reasons, package records,
and full version strings.

## Hosted release boundary

This workflow evaluates source-built CI images. It does not publish images,
call AWS, or authorize a hosted release. The ECR release preflight stays
strict and separate. CI's treatment of unfixed findings does not change that
preflight or waive its checks. Follow the unchanged
[hosted demo process](HOSTED_DEMO.md) for release evidence and authorization.

## Verification

The coordinator runs the CLI fixtures with the backend test dependencies:

```bash
uv run --project backend pytest -q tests/infra/test_image_scan_policy.py tests/infra/test_workflow_pins.py
uv run --project backend ruff check .github/scripts/image-scan-policy.py tests/infra/test_image_scan_policy.py
uv run --project backend ruff format --check .github/scripts/image-scan-policy.py tests/infra/test_image_scan_policy.py
uv run --project backend mypy --strict .github/scripts/image-scan-policy.py
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

The coordinator also runs the workflow linter and independent review.
Fixture results prove policy behavior. They do not prove current image
cleanliness or real AWS release state.
