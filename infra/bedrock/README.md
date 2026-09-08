# Development Bedrock Converse IAM role

This slice defines a Python CDK stack that creates one IAM role. The role
exists so a host caller can assume it and obtain temporary credentials for
nonstreaming Amazon Bedrock `Converse`. The stack does not invoke a model.
The stack does not create an IAM user or access keys.

This draft does not deploy, bootstrap, or change AWS. Do not mount the
deployment admin profile in application containers.

## Boundary

The identity policy grants `bedrock:InvokeModel` only. The current
application calls nonstreaming `Converse`, which uses that action. The
policy does not grant streaming, marketplace subscription, other data-plane
services, or IAM administration.

The stack pins the selected Luna US inference profile. It does not accept
model or region lists. It does not permit a global profile, another model
id, or a resource prefix.

The template describes one development role. It is not a security proof.

## Selected path

Origin region is `us-east-1`. Destination foundation-model regions are
`us-east-1`, `us-east-2`, and `us-west-2`.

The stack builds these ARNs from the stack account:

- `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.openai.gpt-5.6-luna`
- `arn:aws:bedrock:us-east-1:<account>:project/default`
- `arn:aws:bedrock:us-east-1::foundation-model/openai.gpt-5.6-luna`
- `arn:aws:bedrock:us-east-2::foundation-model/openai.gpt-5.6-luna`
- `arn:aws:bedrock:us-west-2::foundation-model/openai.gpt-5.6-luna`

Identity statements:

1. `bedrock:InvokeModel` on the origin profile ARN and the default project ARN.
2. `bedrock:InvokeModel` on the three foundation-model ARNs. The statement
   MUST set `StringEquals` `bedrock:InferenceProfileArn` to the origin
   profile ARN.

Do not put a personal account id in source. Tests use `111122223333`.

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
- `Model=openai.gpt-5.6-luna`
- `ReasoningEffort=low`

The only stack output is `RoleArn`. Outputs MUST NOT include credentials.

## Local ignored `.env`

Copy root `.env.example` to `.env`. Set mode `600`. Git ignores `.env`.
Docker ignores `.env` files. Do not create secrets in the example file.

`.env.example` holds only nonsecret defaults:

- `FEWIA_BEDROCK_MODEL_ID=us.openai.gpt-5.6-luna`
- `FEWIA_BEDROCK_REGION=us-east-1`
- `FEWIA_AWS_PROFILE=fewia-bedrock-dev`

Leave these keys blank until the host helper fills them:

- `FEWIA_BEDROCK_CREDENTIALS_FILE` MUST be an absolute path
- `FEWIA_BEDROCK_ROLE_ARN`
- `FEWIA_BEDROCK_MFA_SERIAL`

Do not put access keys, session tokens, or admin credentials in `.env`.

## Temporary role credentials

Dedicated temporary role credentials live outside the repository at
`~/.config/fewia/bedrock/credentials`. Set mode `600`. A forthcoming host
MFA helper creates that file. This slice does not request an MFA code in
chat. This slice does not implement the helper.

Set `FEWIA_BEDROCK_CREDENTIALS_FILE` to the absolute path of that file.
The helper assumes this role after MFA succeeds. Maximum session duration
is one hour. Renew the session when it expires. Then force-recreate `api`
and `worker`. The bind mount pins the host file inode. The SDK keeps loaded
credentials. An in-process restart MUST NOT replace that mount or those
credentials.

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml \
  up -d --force-recreate api worker
```

The host MUST NOT pass the admin user credentials into containers. Floci
dummy credentials stay separate. Do not set a global `AWS_ENDPOINT_URL`.
Bedrock MUST keep the real regional `bedrock-runtime` endpoint.

The application `modelId` for this path is `us.openai.gpt-5.6-luna`.

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

Cost tracking requires billing activation of IAM-principal tags after the
first Bedrock call. Allow up to 24 hours for the tags to appear. Allow
another 24 hours for activation. See
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
`cdk deploy` in this slice.

```bash
cd infra/bedrock
cdk synth \
  -c account=111122223333 \
  -c region=us-east-1 \
  -c trustPrincipalArn=arn:aws:iam::111122223333:user/dev-caller
```

## Sources

- [GPT-5.6 Luna model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-luna.html)
- [IAM for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html)
- [Bedrock Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [IAM principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html)
- [Grocery Bedrock provider](../../backend/app/providers/bedrock.py)
