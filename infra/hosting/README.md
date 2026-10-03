# Hosting resources

This Python 3.12 CDK project defines undeployed development resources.
Local synthesis writes a CloudFormation template. It creates no AWS resources.
The project uses no AWS clients, credentials, or context lookups.

`HostingResources` exports typed references through `agent_queue`, `agent_dlq`,
`sync_queue`, `sync_dlq`, and `artifact_bucket`. Future stacks can consume these
references. Resource names come from CloudFormation.

Each standard source queue has its own DLQ and a receive limit of three.
Source queues retain messages for four days and use a 120-second visibility
timeout. DLQs retain messages for 14 days. All queues use SQS-managed encryption
and deny insecure transport.

The artifact bucket uses S3-managed encryption, versioning, and all four public
access blocks. Its policy denies insecure transport. It has no lifecycle expiry,
CORS configuration, website configuration, or public access grants.
All five resources retain their data on stack deletion or resource replacement.
The bucket has no automatic object deletion.

`HostingStack` accepts a concrete 12-digit account and only `us-east-1`.
It applies `Project=FEWIA`, `Environment=development`, `ManagedBy=AWS-CDK`,
and `Component=hosting`. Its five outputs contain queue URLs and the bucket name.
Outputs contain no credentials.

## Offline checks

The junior generates `uv.lock` before verification. Python 3.12, Node.js, uv,
and the locked Python dependencies MUST be available locally.
Populate the dependency cache before using the offline commands.
The writer MUST NOT run package tools or checks.

From the repository root, install cached dependencies:

```bash
uv sync --project infra/hosting --offline --frozen
```

From `infra/hosting`, run the project checks:

```bash
uv run --offline --frozen pytest -q
uv run --offline --frozen ruff check .
uv run --offline --frozen ruff format --check .
uv run --offline --frozen mypy --strict .
```

Synthesize locally with a synthetic account from `infra/hosting`:

```bash
CDK_OUTDIR=cdk.out \
  CDK_CONTEXT_JSON='{"account":"111122223333","region":"us-east-1"}' \
  uv run --offline --frozen python app.py
```

The assembly is written to `cdk.out`. Tests use temporary output directories.
Tests validate exact DLQ links, queue settings, TLS policies, bucket controls,
retention policies, tags, outputs, and rejected account or region values.
The resource inventory excludes IAM users, access keys, roles, network resources,
and automatic deletion custom resources. Tests use no live AWS clients.

The coordinator also runs the repository gates from the repository root:

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" \
  --base codex/backlog-resume-gate-cache
```

The current gate router does not run this project's pytest or strict mypy checks.
The coordinator MUST run the project checks separately and record their results.
A separate Codex or Grok agent reviews the result.

## Evidence and scope

Synthesized templates prove resource definitions only. They do not prove real
AWS behavior. Floci SQS and S3 smoke tests provide separate integration evidence;
they do not prove real AWS behavior or deploy these definitions.

This project defines no task roles, ECS services, RDS databases, VPCs, or secrets.
It makes no Bedrock changes. It provides no deployment or bootstrap command.
No AWS mutation is authorized in this work item.
