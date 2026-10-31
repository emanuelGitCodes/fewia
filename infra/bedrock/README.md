# Development Bedrock Converse IAM role

This slice defines a Python CDK stack that creates one IAM role. The role
exists so a host caller can assume it and obtain temporary credentials for
nonstreaming Amazon Bedrock `Converse`. The stack does not invoke a model.
The stack does not create an IAM user or access keys.

Operators MUST NOT run `cdk bootstrap` or `cdk deploy` unless the user
authorizes that action. User-authorized deploy creates the restricted role.
Role deploy does not prove Nova 2 Lite invocation. Do not mount the
deployment admin profile in application containers.

The current target is Amazon Nova 2 Lite with reasoning effort `low`.
A prior Luna access issue is historical. It is not a current permanent block.
This slice does not claim application success.

## Boundary

The identity policy grants `bedrock:InvokeModel` and
`bedrock:ApplyGuardrail` on the guardrail. The current
application calls nonstreaming `Converse`, which uses that action. The
policy does not grant streaming, marketplace subscription, other data-plane
services, or IAM administration.

The stack pins the selected Nova 2 Lite US inference profile. It does not
accept model or region lists. It does not permit a wildcard, another model
id, or a Bedrock project ARN.

The template describes one development role. It is not a security proof.

## Selected path

Origin region is `us-east-1`. Destination foundation-model regions are
`us-east-1`, `us-east-2`, and `us-west-2`.

The stack builds these ARNs from the stack account:

- `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.amazon.nova-2-lite-v1:0`
- `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0`
- `arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0`
- `arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0`

Identity statements:

1. `bedrock:InvokeModel` on the origin profile ARN.
2. `bedrock:InvokeModel` on the three foundation-model ARNs. The statement
   MUST set `StringEquals` `bedrock:InferenceProfileArn` to the origin
   profile ARN.
3. `bedrock:ApplyGuardrail` on the guardrail ARN (see Guardrail below).

The stack MUST NOT grant `bedrock:InvokeModel` on a Bedrock project ARN.

Do not put a personal account id in source. Tests use `111122223333`.

Nova 2 Lite low Converse use is documented in the
[Nova 2 Converse API guide](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-converse-api.html).
The backend and worker set `reasoningConfig`. This stack does not set it.

## Context

Supply these keys. Synth MUST fail when they are missing or inexact.

| Key | Rule |
|---|---|
| `account` | 12-digit account id for the stack environment |
| `region` | `us-east-1` |
| `trustPrincipalArn` | Exact same-account IAM user ARN |

Do not pass `allowedModelArns` or `allowedRegions`. Extra context keys do
not expand the allowlist.

The trust policy names one same-account IAM user. It MUST require
`Bool` `aws:MultiFactorAuthPresent` `true`. It MUST NOT trust account-root,
wildcard, IAM role, or federated principals. Maximum session duration is
one hour.

Tags on the stack:

- `Project=FEWIA`
- `Environment=development`
- `ManagedBy=AWS-CDK`
- `Component=bedrock-chat`
- `Model=amazon.nova-2-lite-v1:0`
- `ReasoningEffort=low`

The stack outputs are `RoleArn`, `GuardrailId`, and `GuardrailVersion`.
Outputs MUST NOT include credentials.

## Guardrail

The stack defines one Bedrock guardrail and one version of it, as decided in
[0025](../../wiki/decisions/0025-medical-claims-and-bedrock-guardrail.md).
It denies four topics:

| Topic | Input | Output |
|---|---|---|
| `MedicalAdvice` | off | on |
| `AllergySafety` | on | on |
| `FinancialTransactions` | on | on |
| `NonFoodTasks` | on | on |

The content filters `HATE`, `INSULTS`, `SEXUAL`, `VIOLENCE`, and
`MISCONDUCT` run at `MEDIUM` on input and output. `PROMPT_ATTACK` runs at
`HIGH` on input and `NONE` on output. Both blocked messages read: "I can
help with meals, grocery lists, nutrition facts, and your food budget. I
cannot help with that request."

The role gains one statement, `ApplyFewiaGuardrail`. It allows
`bedrock:ApplyGuardrail` on the guardrail ARN only.

The owner deploys the stack. Agents MUST NOT deploy, synthesize against an
account, or call AWS. After the owner deploys, copy the `GuardrailId` and
`GuardrailVersion` stack outputs into the local ignored `.env` (or export
them in the shell):

- `FEWIA_BEDROCK_GUARDRAIL_ID=<GuardrailId output>`
- `FEWIA_BEDROCK_GUARDRAIL_VERSION=<GuardrailVersion output>`

`compose.bedrock.yaml` passes both to `api` and `worker`. The guardrail is
off until both are set. Leaving both unset (or empty) keeps it off, and the
Converse request does not change. Setting only one is a configuration error.
Then recreate `api` and `worker` as in the credentials steps above. The
guardrail adds a per-text-unit charge.

A policy edit needs a new guardrail version. After the owner deploys it,
update `FEWIA_BEDROCK_GUARDRAIL_VERSION` to the new `GuardrailVersion`
output and recreate `api` and `worker`.

## Local ignored `.env`

Copy root `.env.example` to `.env`. Set mode `600`. Git ignores `.env`.
Docker ignores `.env` files. Do not create secrets in the example file.

`.env.example` holds only nonsecret defaults:

- `FEWIA_BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0`
- `FEWIA_BEDROCK_REGION=us-east-1`
- `FEWIA_AWS_PROFILE=fewia-bedrock-dev`

Leave these keys blank until the host helper fills them:

- `FEWIA_BEDROCK_CREDENTIALS_FILE` MUST be an absolute path
- `FEWIA_BEDROCK_ROLE_ARN`
- `FEWIA_BEDROCK_MFA_SERIAL`

Do not put access keys, session tokens, or admin credentials in `.env`.

## Temporary role credentials

Dedicated temporary role credentials live outside the repository at
`~/.config/fewia/bedrock/credentials`. Set mode `600`. The host MFA helper
creates that file after MFA succeeds. This slice does not request an MFA
code in chat.

Set `FEWIA_BEDROCK_CREDENTIALS_FILE` to the absolute path of that file.
The helper assumes this role after MFA succeeds. Maximum session duration
is one hour. Renew the session when it expires. Operators MUST run these
steps in order. Use the existing host MFA helper. Then force-recreate
`api` and `worker` with the current Compose override. Then reload nginx.
Cached DNS can otherwise retain the old API container address.

```bash
docker compose -p fewia-grocery-b7d4 --env-file .env -f compose.yaml -f compose.bedrock.yaml \
  up -d --no-deps --force-recreate api worker
docker exec fewia-grocery-b7d4-web-1 nginx -s reload
```

The bind mount pins the host file inode. The SDK keeps loaded
credentials. An in-process restart does not rebind the credentials file.

The host MUST NOT pass the admin user credentials into containers. Floci
dummy credentials stay separate. Do not set a global `AWS_ENDPOINT_URL`.
Bedrock MUST keep the real regional `bedrock-runtime` endpoint.

The application `modelId` for this path is `us.amazon.nova-2-lite-v1:0`.

A configured API and worker do not prove Nova 2 Lite is operational.
Operators MUST NOT treat role deploy as application success.

## Optional Compose override

`compose.bedrock.yaml` overrides `api` and `worker` only. It does not
change Floci, PostgreSQL, or `sync-worker`.

Pass `.env` only for Compose interpolation:

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml up -d
```

Operators MUST NOT mount `~/.aws`. Compose MUST NOT pass the entire
`.env` into a container. The override MUST NOT set
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN`.

The override sets this allowlist:

- `FEWIA_BEDROCK_MODEL_ID`
- `FEWIA_BEDROCK_REGION`
- `FEWIA_AWS_PROFILE`
- `AWS_SHARED_CREDENTIALS_FILE=/run/fewia/aws-credentials`
- `AWS_CONFIG_FILE=/dev/null`
- `AWS_EC2_METADATA_DISABLED=true`

It bind-mounts `FEWIA_BEDROCK_CREDENTIALS_FILE` read-only to
`/run/fewia/aws-credentials`. The bind sets `create_host_path: false`.
Compose MUST fail when that variable is missing or empty. Compose MUST
fail when the host file is missing. Compose MUST NOT create a directory
at that path.

## Cost allocation tags

The role carries cost-allocation tags. Project and Environment billing
keys are active. Model and principal-specific activation waits for AWS
appearance. See
[IAM principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html).

CUR 2.0 caller identity can enable detailed exports. This project does not
configure a CUR export. This stack does not set a spending cap. This stack
does not prove current charges.

## Proposed checks

A separate verifier SHOULD execute these after install is authorized.

`pyproject.toml` sets mypy `strict` and `explicit_package_bases = true`.
Run mypy from `infra/bedrock` so it loads `stack` from this directory.

```bash
cd infra/bedrock
uv sync --group dev
uv run ruff check app.py stack.py test_stack.py
uv run ruff format --check app.py stack.py test_stack.py
uv run mypy --strict app.py stack.py test_stack.py
uv run pytest -q test_stack.py
```

`pytest` synthesizes the stack through `Template.from_stack`. Direct
`python app.py` MUST fail closed without context keys.

A later authorized synth MAY use the CDK CLI with synthetic values. Do not
commit account context. Operators MUST NOT run `cdk bootstrap` or
`cdk deploy` unless the user authorizes that action. User-authorized
deploy creates the restricted role. It does not prove Nova 2 Lite
invocation.

```bash
cd infra/bedrock
cdk synth \
  -c account=111122223333 \
  -c region=us-east-1 \
  -c trustPrincipalArn=arn:aws:iam::111122223333:user/dev-caller
```

## Sources

- [Nova 2 Converse API](https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-converse-api.html)
- [IAM for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html)
- [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [IAM principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html)
- [Grocery Bedrock provider](../../backend/app/providers/bedrock.py)
