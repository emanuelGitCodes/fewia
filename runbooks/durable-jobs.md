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

## Publish a bounded batch

Provision Floci using [the infrastructure runbook](../infra/README.md).
Point `DATABASE_URL` at a database upgraded through migration `0004`.
From `backend/`, run:

```bash
uv run python -m app.publish_jobs --endpoint http://127.0.0.1:4566 --limit 20
```

The publisher owns a fresh transaction per outbox entry. It locks pending
rows with PostgreSQL `SKIP LOCKED`, sends only the job ID, then commits the
publication timestamp. Parallel publishers can select separate rows.
Local SQS calls use explicit dummy credentials and bounded timeouts.

A failed send leaves the entry pending. The batch attempts other entries
within its limit, then raises `PublicationError` with success/failure counts.
The command exits unsuccessfully when any send failed. Database commit errors
also propagate. A crash after send but before commit can cause a duplicate
on the next run; delivery is at least once. Workers must deduplicate by job ID.
The default batch processes at most 20 entries; the maximum is 100.

Run the additional concurrency check against an isolated migrated PostgreSQL:

```bash
uv run pytest tests/test_outbox_postgres.py -q
```

Set `FEWIA_JOB_TEST_DATABASE_URL` as described above. This test uses fake
senders synchronized while holding separate row locks; it does not send
provider data or call Floci.

## Job leases

`backend/app/services/job_leases.py` provides `claim_job`, `renew_lease`, and
`finish_job`. Each helper uses conditional SQL updates in the caller's
transaction. The caller MUST commit a claim before starting job execution.
The caller MUST use short transactions and supply a fresh timezone-aware
`now` for each operation. Helpers normalize that time to UTC.
The helpers do not synchronize loaded ORM objects. Callers MUST refresh or
expire loaded jobs before reading their updated fields.

A queued job or an expired running job can receive a fresh lease token.
Each claim increments attempts. An active or terminal job cannot be claimed.
An eligible job at the attempt limit becomes failed with `attempts_exhausted`.
The default limit is three attempts; the accepted range is one through 100.
Lease duration defaults to 60 seconds and accepts one through 3,600 seconds.

Renewal and completion require the current token and an unexpired running
lease. Expiry equal to `now` permits reclaim and rejects the previous owner.
Renewal does not shorten the existing expiry. Completion clears lease fields.
An error code marks failure; otherwise completion marks success. A partial
result can accompany an error. Omitting a result preserves its stored value.
Callers MUST sanitize results and error codes.

The caller MUST commit durable results before acknowledging a queue message.
Lease tokens protect database transitions. They do not undo external side
effects or make an uncertain provider write safe to retry.

Run the lease concurrency and rollback checks against the isolated database:

```bash
uv run pytest tests/test_job_leases.py tests/test_job_leases_postgres.py -q
```

## Run the worker

`backend/app/worker.py` runs one worker for one job kind. Compose starts
two: `worker` (`--kind agent`) and `sync-worker` (`--kind sync`). Each uses
`http://floci:4566` inside Compose. From the host, Compose publishes Floci
on port 4567 (`FLOCI_HOST_PORT`). Run one worker by hand from `backend/`:

```bash
uv run python -m app.worker --endpoint http://127.0.0.1:4567 --kind agent
```

`--transport aws` selects real SQS. SIGINT or SIGTERM stops the loop after
the current job. The worker runs the outbox publisher in a background
thread, so a separate `app.publish_jobs` run is not necessary.

Each loop pass does two steps:

1. `recover_jobs` in `backend/app/services/job_recovery.py` takes at most
   20 stale jobs. A stale job is a running job with an expired lease, or a
   queued job whose message was published at least 300 seconds ago. A job
   at three attempts becomes failed with `attempts_exhausted`. A job whose
   payload `job_replay_safe` rejects becomes failed with
   `recovery_required`. Any other stale job returns to `queued`, and its
   outbox entry is cleared for publication again.
2. `process_one` in `backend/app/services/job_consumer.py` handles one
   message. An empty queue makes the worker wait one second.

## Delivery and failure handling

Two mechanisms protect a job. The SQS visibility timeout controls when a
message returns to the queue. The database lease controls which worker
can write the job. The timings nest: a 15-second heartbeat, a 60-second
lease, and a 120-second visibility timeout.

| Event | Database lease | Queue message |
|---|---|---|
| `claim_job` returns a token | The job runs | Stays hidden |
| The job is terminal or exhausted | No claim | Acknowledged |
| Another worker holds an active lease | No claim | Visibility extended 120 seconds |
| Heartbeat, every 15 seconds | `renew_lease` | Visibility extended 120 seconds after the renewal commits |
| `renew_lease` fails | The worker drops the job (`lease_lost`) and takes the next message | Not acknowledged or extended; it returns when its current timeout ends |
| `RetryableJobError` | Lease runs out | Visibility extended 120 seconds; not acknowledged |
| `JobFailure` or another exception | Renewal, then `finish_job` with an error code | Acknowledged; if the renewal or `finish_job` fails, handled as `lease_lost` |
| Success | `finish_job` commits the result | Acknowledged after the commit; if `finish_job` fails, handled as `lease_lost` |

A redelivered message for a finished job is acknowledged without a new run,
so duplicate delivery is safe. After three receives, SQS moves the message
to the dead-letter queue (`fewia-agent-dlq` or `fewia-sync-dlq`). The
[infrastructure runbook](../infra/README.md) defines both queues.

A lost lease does not stop a provider call that is already in progress.
A handler that writes to a provider MUST make that write idempotent, or a
retry can repeat it.

## Migration rollback

Migrations `0001` through `0004` have working `downgrade()` bodies.
Migrations `0005`, `0006`, and `0007` are forward-only. Their `downgrade()`
raises `RuntimeError`. Do not downgrade below `0007` on a database that holds
data. Restore from a backup instead. Migration `0007` creates a PostgreSQL
trigger function with raw SQL, so `alembic check` does not see it.
