# Durable job submission

The application stores a job and its queue-publication marker together.
`create_job` in `backend/app/services/job_submission.py` returns the job and
a boolean that identifies a new insertion. The caller commits or rolls back.
The helper does not send SQS messages.

## Idempotency

The request key is scoped to a user and a job kind (`sync` or `agent`).
It contains at most 128 characters and cannot be blank.
The same key with the same canonical JSON returns the existing job unchanged.
The same key with different content raises `IdempotencyConflict`.
JSON object order does not change content; a boolean and a number differ.

A database uniqueness constraint resolves simultaneous requests. A nested
transaction rolls back a failed insertion without discarding caller writes.
The outbox insert belongs to the same transaction as its job insert.

The concurrency contract uses PostgreSQL's default `READ COMMITTED` isolation.
Higher isolation levels need caller-managed serialization retries. SQLAlchemy
flushes pending caller changes before opening a nested transaction; the helper
does not commit them. The caller rolls back the outer transaction on failure.
Production job writers must use this helper to maintain the outbox invariant.
Repair of rows inserted without an outbox is a separate reconciliation task.

Callers supply validated, sanitized payloads. JSON validation is not secret
redaction. Do not put credentials, raw provider responses, or hidden model
reasoning into a job. Queue messages will contain only the job ID.

## Verification

From `backend/`, run the normal test suite:

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

The PostgreSQL tests are opt-in. Set `FEWIA_JOB_TEST_DATABASE_URL` to a
disposable PostgreSQL database upgraded through migration `0004`.
Then run:

```bash
uv run pytest tests/test_job_submission_postgres.py -q
```

These tests synchronize competing inserts to force a uniqueness race and
verify caller rollback from a separate session. They insert synthetic users
and delete only those users' test jobs and outbox records afterward.
They do not apply migrations. Do not target the shared development database.

## Remaining worker work

The next slices publish committed outbox records through Floci SQS, acquire
job leases, renew visibility, and persist terminal results. Storage and
submission alone do not implement a running background worker.
