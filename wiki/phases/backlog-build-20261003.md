# Backlog build checkpoint

- Date: 2026-10-03
- Source revision: `be7470aac8212dc297ac8c651e643e272cf1aec2`
- Publication: branches and pull requests authorized; merges are not authorized.
- Stop condition: stop model work at 8 percent total weekly Codex usage.
- Starting weekly usage: 1 percent.

## Status

This record separates source inspection from runtime verification.
Open pull requests do not establish that a change reached `main`.

| Item | State | Evidence or next step |
|---|---|---|
| A1 | Reconciled locally | Track the corrected ledger copies on this branch; independent review is pending. |
| A2 | Open | Alembic lint passes. CI omits that path. The backend image already copies migrations. |
| A3 | Present and checked locally | Both audit commands use `--no-deps`. Import and line-length lint passes. |
| A4 | Awaiting retention choice | No data deletion is authorized by this build. |
| A5 | Present and tested | Quantity and serving scaling already exists; nutrition and catalog tests pass. |
| A6 | Present and tested | Session counter reset and pre-launch recovery already exist; focused tests pass. |
| A7 | In progress | Direct polling-hook tests are missing. Spoonacular catalog tests already exist. |
| B1 | In progress | Add automatic review fallback with explicit provenance. |
| B2 | Open | Historical compatibility commit is `c9316dad200186d1c8421870e8cabbcd01c19232`. |
| B3 | Open | Record this loop's measured usage against the historical pilot baseline. |
| B4 | Open | Browser checks need screenshots and recorded results. |
| B5 | In progress | Render canonical batch evidence and separate legacy fixture coverage. |
| C1 | Open | Implement slot dispatch after the report contract is fixed. |
| C2 | Open | Implement the 138-slot batch after C1. |
| C3 | Open | Implement the opt-in CLI after C2 and B5. |
| C4 | Open | Build the fixture-only handoff flow. |
| D1 | Blocked by C1 to C3 | Fixture and live benchmarks have not run in this build. |
| D2 | Blocked by D1 | Record final benchmark artifacts only after execution. |
| D3 | Blocked by D1 | The paper needs benchmark evidence. |
| D4 | Paused by product decision | Plaid Sandbox remains the last feature. |
| D5 | Open | Each mutating AWS step needs owner confirmation. |

## Local checks

- `uv run --project backend pytest -q backend/tests/test_meal_nutrition.py backend/tests/test_spoonacular_catalog.py`: 24 passed, one Starlette warning.
- `PYTHONPATH=.:backend uv run --project backend pytest -q backend/tests/test_database_gate.py tests/supervisor/test_lease.py tests/supervisor/test_execution.py`: 36 passed, one Starlette warning.
- `uv run --project backend ruff check backend/alembic`: all checks passed.
- `uv run --project backend ruff check --select I,E501 backend/app backend/tests dev_supervisor tests infra --exclude infra/bedrock`: all checks passed.

These commands used a temporary uv cache. An initial combined pytest command
failed collection without the repository root on `PYTHONPATH`. The corrected
command above passed. These focused checks do not replace each changed
branch's gates or its independent review.

## Runtime isolation

The container `fewia-backlog-20261003-postgres` belongs to this build.
Its host port is 55447. Existing FEWIA containers remain untouched.
The build creates no deployed AWS evidence.
