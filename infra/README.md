# Local Floci foundation

Floci provides the grocery bot's local SQS and S3 resources. PostgreSQL remains
the application database. This foundation does not yet implement the worker,
Plaid adapter, Instacart adapter, Bedrock loop, or web chat.

## Start and provision

Run these commands from the repository root:

```bash
uv sync --project backend --locked
docker compose up -d --no-deps floci
uv run --project backend python -m infra.floci_bootstrap --endpoint http://127.0.0.1:4566
```

The bootstrap prints the two queue URLs and the artifact bucket name.
Repeat the bootstrap safely to reconcile the resource settings.

| Resource | Purpose |
|---|---|
| `fewia-sync` | Background Plaid synchronization jobs |
| `fewia-sync-dlq` | Exhausted synchronization jobs |
| `fewia-agent` | Background grocery agent jobs |
| `fewia-agent-dlq` | Exhausted grocery agent jobs |
| `fewia-eval` | Sanitized evaluation exports |

Both source queues use a 120-second visibility timeout and a three-receive
dead-letter policy. The future worker will extend visibility for active jobs.
Queue provisioning alone does not implement leases, retries, or durable jobs.

## Client boundary

The bootstrap accepts only `http://127.0.0.1:4566`,
`http://localhost:4566`, and `http://floci:4566`. Other endpoints fail before
client creation. It supplies explicit local dummy credentials and region.
It does not read real AWS credentials for its default clients.

The Compose service advertises `floci` in returned queue URLs so other
containers can resolve them. Host callers still configure the SQS client's
endpoint as `http://127.0.0.1:4566`. Queue URLs identify resources; do not use
the container hostname as a host-machine service endpoint.

Do not set a global `AWS_ENDPOINT_URL`. The future Bedrock provider requires
its own real endpoint and credentials. Floci does not prove Bedrock behavior.

## Persistence and lifecycle

Compose pins Floci 2.0.1 to a verified image digest. The `floci-data` named
volume holds persistent emulator state. Port 4566 binds to loopback.

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
