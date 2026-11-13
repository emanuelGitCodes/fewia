# Security hardening handoff

Date: 2026-11-12. Branch: `codex/security-hardening`. Base: `cad31e86`.
Source snapshot: `94a5ec3fa04e0bdc0485a62858d0538dc5d2855f`.

## Status

The owner requested a usage cutoff and one pull request containing the saved work.
Implementation stopped. All workstream changes are committed on the final branch.
The source snapshot changes 236 files, with 30,404 additions and 2,594 deletions, including tests and documentation.
The owner approved the size exception in [decision 0031](decisions/0031-security-hardening-and-hosted-accounts.md).

Publication is pending. The repository hook rejected the push from Codex.
Its reason was: "Codex hooks cannot ask: give the command to the user to run."
No pull request or merge exists at this checkpoint. The target is one draft pull request against `main`.
The draft MUST remain unmerged until the remaining checks pass.
The account meter reported 21% usage in a 10,080-minute weekly window. It exposed no daily window or task-specific usage.

## Saved implementation

- Signed ALB identity, hosted account provisioning, ownership checks, session discovery, and sign-out.
- Browser workspace isolation, request preconditions, origin checks, and private response caching rules.
- Local Kroger pairing, one-use OAuth state, signed cart previews, and durable cart outcomes.
- Database-derived worker ownership, lease fences, durable effects, and atomic job admission.
- Model concurrency limits, conservative cost reservations, versioned rates, and provider response bounds.
- Server-rendered factual replies, restricted USDA queries, and synthetic-only detailed evaluation exports.
- Separate local database credentials, private files, runtime grants, and forward-only migrations.
- Operator retention controls, dependency upgrades, image context exclusions, and image scan gates.

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

The earlier full-suite skip covered a PostgreSQL 17 privilege check on PostgreSQL 16.
Earlier snapshots do not establish final acceptance. No live Cognito, Kroger, model, or AWS deployment check ran.

## Release blockers

1. Repair gates and CI setup for the new private local-state variables. The persistent helper change is absent.
2. Complete `.agents/skills/gates/scripts/gates-with-db.sh --base main` on the final committed SHA, with database tests enabled.
   Investigate the prior timeout before attributing it only to the environment.
3. Complete independent Terra review of the combined boundaries and final SHA. Repeat regression and mutation probes after repairs.
4. Resolve container findings and scan the exact release digests.
   Local arm64 candidates reported 98 backend, 45 frontend-build, and 52 frontend-runtime HIGH/CRITICAL findings.
   A Debian Trixie probe still reported 18 HIGH findings without listed fixes.
   The amd64 emulated scan exceeded 15 minutes and stopped. No clean release scan exists.
5. Verify hosted sign-out end to end. The Cognito logout allowlist still returns to `/`.
   Confirm that ALB authentication does not immediately sign the user back in.
6. Reconcile the operator guides with the new flows. Complete Floci smoke checks and integrated browser journeys.

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
