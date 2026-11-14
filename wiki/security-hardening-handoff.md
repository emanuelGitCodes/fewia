# Security hardening handoff

Date: 2026-11-13. Branch: `codex/security-hardening`. Base: `cad31e86`.
Verified and reviewed source checkpoint: `956c0f908c8cc17cd6b4bdb43b654234e8a6728d`.

## Status

The owner resumed work with 15 additional weekly percentage points from the original 21% baseline.
The cutoff is 36%. The meter reached that cutoff after the final review finished.
Implementation stopped. The final documentation commit records the review; it does not change the reviewed source.
The owner approved the size exception in [decision 0031](decisions/0031-security-hardening-and-hosted-accounts.md).

The owner published the checkpoint through the terminal after the repository hook rejected Codex publication.
[Pull request 494](https://github.com/emanuelGitCodes/fewia/pull/494) is open as the single draft against `main`.
The owner then authorized a separate, bounded hook change to recognize explicit approval for a scoped publication command.
That authorization does not resume the unresolved application-security repairs or authorize a merge.
The draft MUST remain unmerged until the remaining checks pass.
The account meter exposes a 10,080-minute weekly window, with no daily window or task-specific usage.

## Saved implementation

- Signed ALB identity, hosted account provisioning, ownership checks, session discovery, and sign-out.
- Browser workspace isolation, request preconditions, origin checks, and private response caching rules.
- Local Kroger pairing, one-use OAuth state, signed cart previews, and durable cart outcomes.
- Database-derived worker ownership, lease fences, durable effects, and atomic job admission.
- Model concurrency limits, conservative cost reservations, versioned rates, and provider response bounds.
- Server-rendered factual replies, restricted USDA queries, and synthetic-only detailed evaluation exports.
- Separate local database credentials, private files, runtime grants, and forward-only migrations.
- Operator retention controls, dependency upgrades, image context exclusions, and a frontend runtime image scan gate.

This list describes committed code. It does not establish deployed security or final acceptance.

## Verification record

| Scope and snapshot | Observed result |
| --- | --- |
| Integrated source `94a5ec3f` | Every integration commit passed Gitleaks. `git diff --check cad31e86..HEAD` passed. |
| Integrated backend `94a5ec3f` | Ruff passed; 437 files passed formatting; strict mypy passed for 213 source files. |
| Integrated provider and retention tests `94a5ec3f` | OpenAI, Bedrock, and retention transport modules: 405 passed, one deprecation warning. |
| Earlier complete gates `99675b0d` | Backend: 18,848 passed, one skipped. Frontend lint, tests, and build passed. |
| Later combined gates `2cfc0b9b` | Backend pytest exceeded 900 seconds. The gate failed. Lint, formatting, and strict typing passed. |
| Frontend `678e30de` | Node 22.23.0: lint and build passed; 1,261 tests passed. |
| Browser `97a4af49`, frontend `678e30de` | 22 Chromium journeys passed across desktop and mobile sizes. Identity and provider responses were mocked. |
| PostgreSQL ownership `b2524aaf` | 12 endpoint tests passed with signed identities and the runtime database role. |
| Workspace preconditions `4016dfbc` | 345 PostgreSQL-backed tests passed. |
| Live quote admission `0105fce5` | 116 PostgreSQL-backed tests passed. |
| Local infrastructure `db3f3101` | 160 tests passed, one skipped. A separate synthetic PostgreSQL credential-upgrade test passed. |
| Hosted infrastructure `f4164a00` | 1,887 tests and four Nginx tests passed. Lint and strict typing passed. |
| Provider transport `6dad2e06` | 537 fake-provider tests passed. Lint and strict typing passed. |
| Dependencies `5a7a2391` | npm and Python audits found no known vulnerabilities in the checked dependency sets. |
| Security mutation probes | Signature, expiry, database grants, and HTTP body-cap mutations caused the expected test failures. |
| Independent review | Terra approved HTTP snapshot `22d31250`. No review approved the final combined source snapshot. |
| Resumed backend boundary review `e13c6ac1` | Terra returned APPROVE for inspected authentication, ownership, admission, effects, cost, and retention boundaries. This was not final release approval. |
| Hosted sign-out `9223388c` | 1,906 hosting tests passed. Synthetic Chromium verified cookie deletion, protected API routes, and explicit sign-in at two viewport sizes. |
| Combined gates `88d515b8` | RESULT PASS: 20,301 backend tests, 585 tooling tests, 1,906 hosting tests, frontend lint/tests/build, and Compose validation. Alembic found no drift. |
| Frontend framework repair | All 1,265 tests passed, including the four Nginx assertions through Vitest. |
| New mutation probes | Removing TCP readiness, required database settings, or the job-effect metadata guard caused the expected regression failures. |
| Exact source checkpoint `956c0f90` | All gates passed, including fresh frontend dependency installation, 20,301 backend tests, 585 tooling tests, 1,906 hosting tests, and Compose. |
| Final Terra review `956c0f90` | REQUEST_CHANGES: two blocking Kroger connection races. No repair started after the usage cutoff. |

The combined gate skipped the opt-in Compose credential rotation test and a PostgreSQL 17 privilege check on PostgreSQL 16.
The separate synthetic credential-upgrade test passed earlier. Required PostgreSQL tests ran in the combined gate.
The exact source checkpoint has its gate record under `.fewia-supervisor-gates`.
Its review is in `/private/tmp/fewia-security-final-review/.fewia-supervisor-reviews`.
The final documentation commit adds these outcomes; it does not have a separate source review.
No live Cognito, Kroger, model, or AWS deployment check ran.

## Release blockers

Terra flagged two blocking races in `backend/app/api/kroger.py` at the reviewed checkpoint:

- Around line 317, an older OAuth exchange can overwrite a newer retailer connection after an overlapping exchange completes.
- Around line 410, preview lookup can span a reconnect and receive a confirmation bound to the new connection.

These are review findings, not results from live-provider probes. They remain unresolved.
The next repair MUST fence each operation against the connection state captured when that operation starts.
Regression tests MUST exercise overlapping exchanges and reconnects during preview lookup.

1. Resolve container findings and scan the exact release digests. No clean backend or toolchain release scan exists.
2. Complete Linux amd64 release-image scans. Local native-arm64 evidence does not establish hosted-image acceptance.
   The GitHub image workflow scans the frontend runtime image only. The owner removed the backend runtime, frontend toolchain, and frontend build targets on 2026-11-13.
   No CI check reports their findings. The release scan in item 1 MUST cover those three images.
3. Complete live Cognito sign-out and account isolation checks, Floci smoke checks, and deployed browser journeys before hosted activation.
4. Repair both review findings, repeat their race tests and the gates, and obtain independent approval before marking the draft ready.

The resumed work repaired private Compose fixtures, TCP readiness, test failure diagnostics, metadata drift, legacy regression fixtures, and test discovery.
Hosted logout now returns to an exact public `/signed-out` ALB fixed response. It forwards no request to the application.
The operator guides now describe hosted accounts, credential migration, owner pairing, and signed confirmation.

### Image evidence

Trivy 0.76.2 used a database updated at `2026-11-13T07:00:07Z`.
The table counts unique HIGH/CRITICAL package-CVE pairs from retained native-arm64 reports.
These are local candidate configuration digests, not hosted release attestations.

| Candidate | Configuration digest | Findings |
| --- | --- | --- |
| Backend runtime | `sha256:6ba81ce8514e026602de92ba9049f68b114433a32fa2015b91e6658ef8e3732f` | 98; Debian reports no fixed versions. |
| Frontend build before toolchain separation | `sha256:3404ff479421ef0027171369bb3667c56ab516978fc82abf5c36aa77a6c6d269` | 35; Debian reports no fixed versions. |
| Frontend runtime candidate | `sha256:321c2bb1c073fe1329f479c4a31219e85955b59835715b6ea5ce341faa6f19c2` | 0. |
| Final dedicated toolchain | `sha256:0ca36339d7a33a8a3fe454b753fff79c773e536195ab54c26d9b572e2c9f386c` | 44; Debian and bundled bootstrap npm remain visible. |

The toolchain uses npm 12.2.2 with engine enforcement and preserves bundled npm for scanning.
The coordinator verified that its Trivy image identity matches the archive configuration hash.
Retained reports are in `/private/tmp/fewia-image-current-2026-11-13`.
No vulnerability suppression was added. Hosted activation remains blocked.

### Graphify

The requested refresh updates the full supported corpus incrementally and preserves unchanged source references.
The graph contains about 17,000 nodes. Local artifacts are in ignored `graphify-out/`.
The report names the exact source SHA, manifest status, extraction coverage, and diagnostics.
The detector skips `secrets.yml` and the RDS certificate bundle. The unchanged PDF retains prior records.
Published graph endpoints resolve; self-loops and raw extraction limits remain explicit in the report.

Deployment and live-provider validation remain separate release steps. This checkpoint grants no deployment approval.

## Migration and recovery

These instructions describe the committed migration path. Final release verification remains open.

For local data:

1. Back up PostgreSQL and verify restoration. Keep the existing Compose project and volume names.
2. Keep `.env` as a regular file with mode `0600`. Use the same nonroot host user that owns the checkout.
3. After release acceptance, use `make up` for fixtures or `make up-kroger-live` for the configured live retailer flow.
4. Preserve `.fewia-state` with mode `0700`, its files with mode `0600`, and `.env0600` with mode `0600`.
5. The launcher stops API and worker services, then rotates the administrator password through the container's local PostgreSQL socket.
   Bootstrap migrates the database, preserves user 1, and provisions the restricted runtime role.
6. Wait for bootstrap success and API health. The base configuration exposes neither PostgreSQL nor Floci on the host.
   The tools overlay exposes Floci on loopback.

The operator MUST NOT delete volumes to fix credential errors or print secret files in reports.
After failure, keep application services stopped while checking file modes, ownership, and bootstrap status.
Restore lost private files from the matching backup. With intact files, the launcher repeats rotation and bootstrap without replacing the volume.
If local-socket administration fails, recover the database with the preserved volume and verified backup.

For hosted data, stop old API and worker versions before migration or tenant traffic. Mixed-version execution is unsupported.
Run `alembic upgrade head` with the administrator connection in the backend environment.
Reapply runtime grants through `app.runtime_database_access` before starting runtime services.
Migrations 0012 through 0018 add identity, quota, admission, effect, cost, and retention records.
User 1 stays reserved. Hosted login does not claim or reassign existing records.
Configure the exact ALB signer, Cognito issuer and client, and public origins before enabling traffic.
Activate traffic only after final review and completed scans of the exact image digests.
Rollback requires a verified backup and planned recovery. Do not downgrade the schema in place.

No automatic purge runs. Operators use `python -m app.retention_admin` with a separate operator connection.
Preview and purge require the owner and cutoff; purge also requires the matching preview digest.
Remote connections require `sslmode=verify-full` and an explicit CA path.
Active work and unresolved dependencies can block deletion. No retention command ran against user data during this task.

## Resume

Resume the `security-hardening` loop on this branch. Keep one pull request, the publication guards, and final review.
The ignored loop ledger records local worktree and evidence locations.
