# Local Floci foundation

Floci provides the grocery bot's local SQS and S3 resources. PostgreSQL remains
the application database. The worker, the sync worker, and the API use these
resources in the default Compose stack.

## Start and provision

Run this command from the repository root:

```bash
docker compose up -d
```

The one-shot `bootstrap` service waits for a healthy Floci and PostgreSQL.
It provisions the queues and the artifact bucket through
`http://floci:4566`. Repeat the bootstrap safely to reconcile the resource
settings:

```bash
docker compose run --rm bootstrap
```

The host port for Floci defaults to 4567 (`FLOCI_HOST_PORT`). The bootstrap
accepts only 4566 endpoints, so run it inside Compose, not from the host.

| Resource | Purpose |
|---|---|
| `fewia-sync` | Background Plaid synchronization jobs (Plaid work is paused) |
| `fewia-sync-dlq` | Exhausted synchronization jobs |
| `fewia-agent` | Background grocery agent jobs |
| `fewia-agent-dlq` | Exhausted grocery agent jobs |
| `fewia-eval` | Sanitized evaluation exports |

Both source queues use a 120-second visibility timeout and a three-receive
dead-letter policy. The worker extends visibility for active jobs. See
[runbooks/durable-jobs.md](../runbooks/durable-jobs.md) for leases and retries.

## Client boundary

The bootstrap accepts only `http://127.0.0.1:4566`,
`http://localhost:4566`, and `http://floci:4566`. Other endpoints fail before
client creation. It supplies explicit local dummy credentials and region.
It does not read real AWS credentials for its default clients.

The Compose service advertises `floci` in returned queue URLs so other
containers can resolve them. Host callers configure the SQS client's
endpoint as `http://127.0.0.1:4567`, or the `FLOCI_HOST_PORT` value. Queue URLs identify resources; do not use
the container hostname as a host-machine service endpoint.

Do not set a global `AWS_ENDPOINT_URL`. The Bedrock provider requires its
own real endpoint and credentials. Floci does not prove Bedrock behavior.

## Persistence and lifecycle

Compose pins Floci 2.0.1 to a verified image digest. The `floci-data` named
volume holds persistent emulator state. The host port binds to loopback.

```bash
docker compose stop floci
docker compose start floci
```

These commands preserve emulator state. Do not remove volumes when stopping
the service. Existing API and PostgreSQL containers need no recreation for
this foundation check.

## Checks

```bash
docker compose config --quiet
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run ruff check --config pyproject.toml ../infra
uv run ruff format --check --config pyproject.toml ../infra
uv run mypy --strict app
uv run pytest
```

Unit tests use injected fake AWS clients. A live smoke check also needs to
send, receive, and acknowledge a dummy message on each queue, read back both
redrive policies, and upload/download a harmless artifact from `fewia-eval`.
Repeat resource reads after restarting Floci to check persistence.

Only synthetic smoke data belongs in the local emulator. Provider access
checks remain separate from queue and bucket tests.

## Sources

- [Floci repository](https://github.com/floci-io/floci)
- [Accepted grocery scope](../.codex/project-context.md)
