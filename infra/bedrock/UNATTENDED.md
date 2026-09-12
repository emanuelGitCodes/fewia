# Unattended Bedrock runtime IAM user

This slice defines a separate Python CDK stack. The stack creates one IAM
user for local FEWIA to call Amazon Bedrock without a human MFA prompt.
The stack does not invoke a model. The stack does not create access keys.

This path is not IAM Roles Anywhere. This path is not personal MFA.
A user-approved long-lived IAM application access key trades automatic
hourly expiry for rotation and revocation.

The current human-MFA stack `FewiaBedrockDev` MUST remain unchanged.
Keep the host MFA helper available for that role. Do not mount the
deployment admin profile in application containers.

The coordinator verified the live stacks and the local Compose runtime.
This file does not contain credentials.
This file does not claim Cost Explorer charges.

## Boundary

Operators MUST synthesize this stack through `workload_app.py`.
That entrypoint instantiates `FewiaBedrockRuntime` only.
It MUST NOT instantiate `FewiaBedrockDev`.
It MUST NOT instantiate `FewiaBedrockRuntimeDeployment`.

Operators MUST create the dedicated CloudFormation execution role first.
Follow `DEPLOYMENT.md` for stack `FewiaBedrockRuntimeDeployment`.
The shared CDK bootstrap execution role has no IAM user lifecycle
permission. Operators MUST NOT widen that shared role.

`workload_app.py` selects `DefaultStackSynthesizer` with an empty
`deploy_role_arn`. It sets `cloud_formation_execution_role` to
`arn:aws:iam::<account>:role/fewia-bedrock-runtime-deployment`.
Empty `deploy_role_arn` selects the CLI caller to submit CloudFormation.
The CLI caller MUST be the chosen aws-admin identity.
The synthesizer sets `generate_bootstrap_version_rule=False`.
That setting removes automatic SSM bootstrap lookup.
The runtime user stack MUST NOT add SSM permission.

```bash
cd infra/bedrock
cdk synth --app "python3 workload_app.py" \
  -c account=111122223333 \
  -c region=us-east-1
```

Replace the synthetic account with the 12-digit target account at deploy
time. Do not commit a real account id.

Operators MUST NOT run `cdk bootstrap` or `cdk deploy` unless the user
authorizes that action. User-authorized deploy creates the restricted
user. It does not create an access key.

Context keys:

| Key | Rule |
|---|---|
| `account` | Exact 12-digit AWS account id |
| `region` | `us-east-1` |

Synth MUST fail when those values are missing or inexact.

## Identity

The stack creates IAM user `fewia-bedrock-runtime` at path `/fewia/`.
The user has no password. The user has no login profile. The user joins
no groups. CloudFormation MUST NOT emit an access key.
CloudFormation MUST NOT emit a secret.

The user resource uses removal policy `RETAIN`. Stack delete does not
remove the user. Operators MUST manage that retained user explicitly.

The inline policy lives on the user. The policy grants
`bedrock:InvokeModel` only:

1. Origin profile
   `arn:aws:bedrock:us-east-1:<account>:inference-profile/us.amazon.nova-2-lite-v1:0`.
2. Foundation models in `us-east-1`, `us-east-2`, and `us-west-2` for
   `amazon.nova-2-lite-v1:0`. That statement MUST set `StringEquals`
   `bedrock:InferenceProfileArn` to the origin profile ARN.

The identity MUST NOT receive wildcard actions or wildcard resources.
The identity MUST NOT receive STS, IAM, S3, Plaid, or billing actions.
The identity MUST NOT receive a console password.
The identity MUST NOT receive IAM groups or managed policies.
The identity MUST NOT receive IAM administrator, S3, or billing grants.

Outputs are `UserArn` and `UserName` only. Outputs MUST NOT include keys.

Tags on the stack and the user:

- `Project=FEWIA`
- `Environment=development`
- `Component=bedrock-chat`
- `ManagedBy=AWS-CDK`
- `Model=amazon.nova-2-lite-v1:0`
- `ReasoningEffort=low`
- `CostCenter=FEWIA`

## Verified deployment

Live CloudFormation status:

Stack `FewiaBedrockRuntimeDeployment` is `UPDATE_COMPLETE`.
Role `fewia-bedrock-runtime-deployment` trusts
`cloudformation.amazonaws.com` only.
The role grants 14 user lifecycle and metadata actions on the pathed
runtime user ARN.
The role grants `iam:GetUser` and `iam:GetUserPolicy` only on the
unpathed same-name ARN for pre-creation checks.
The role MUST NOT grant those reads on any other user name.
The role MUST NOT use wildcards.

Stack `FewiaBedrockRuntime` is `CREATE_COMPLETE`.
IAM user `fewia-bedrock-runtime` exists at path `/fewia/`.
CloudFormation and CDK own that user.
Operators MUST NOT create that user by a console click.

Both IAM resources use removal policy `RETAIN`.
Both stacks and both IAM resources carry seven tags.
Shared keys are `Project=FEWIA`, `Environment=development`,
`ManagedBy=AWS-CDK`, `Model=amazon.nova-2-lite-v1:0`,
`ReasoningEffort=low`, and `CostCenter=FEWIA`.
The user and the user stack set `Component=bedrock-chat`.
The role and the role stack set `Component=bedrock-deployment`.

The existing human MFA role stays unchanged.
That role still requires MFA.
Maximum session duration stays 3600 seconds.
The shared MLOps bootstrap role attachments stay unchanged.

IAM simulation on the runtime user allows the selected US Nova 2 Lite
profile.
IAM simulation implicit-denies another model.
IAM simulation implicit-denies `iam:CreateUser`, `s3:GetObject`, and
`ce:GetCostAndUsage`.

The coordinator created one IAM application access key outside Git.
Path: `~/.config/fewia/bedrock/runtime-credentials`.
Parent directory mode: `700`. File mode: `600`.
Profile name: `fewia-bedrock-runtime`.
The file holds exactly two fields.
The file MUST NOT hold a session token.
The file MUST NOT hold `DEFAULT` fields.
The file MUST NOT hold another profile.
This key is long-lived.
This key is not IAM Roles Anywhere.
Operators MUST rotate or revoke this key.
This path does not use hourly STS.
This path does not use MFA for application containers.
Operators MUST NOT obtain the personal admin MFA secret for this path.

`.env` holds metadata pointers only.
`.env` MUST NOT hold access keys or secret values.

## Application access key

The coordinator MUST create the access key only after user authorization.
The coordinator MUST write the secret only to the host credentials file.
The coordinator MUST NOT print the secret to stdout, logs, or chat.
Commands MUST NOT echo access keys. The launcher MUST NOT create a key.
The launcher MUST NOT modify AWS. An administrator generates the key
outside this code.

Store the file outside the repository:

- Path: `~/.config/fewia/bedrock/runtime-credentials`
- Parent directory mode: `700`
- File mode: `600`
- Profile name: `fewia-bedrock-runtime`

The file uses the shared credentials format. The file MUST contain only
profile `fewia-bedrock-runtime`. The file MUST NOT contain `DEFAULT`
fields. The file MUST NOT contain a session token. The file MUST NOT
contain another profile. Do not put a console password in the file.
Do not put the admin profile in the file.

Do not write host `.env` for this path. Do not use
`compose.bedrock.yaml` on this path. That generic override allows a
blank `FEWIA_AWS_PROFILE`. It also allows a relative credential path.

## Current usage

Operators MUST start the base Compose services first. Run the
validated launcher from the source checkout. That checkout owns
`infra/bedrock_runtime.py` and `compose.bedrock-runtime.yaml`.
Prefer this launcher for local development.
Keep `compose.bedrock.yaml` for a human MFA session only.

```bash
python -m infra.bedrock_runtime --checkout /path/to/fewia --project fewia-macros
python -m infra.bedrock_runtime --checkout /path/to/fewia --project fewia-grocery-b7d4
```

Replace `/path/to/fewia` with the source checkout or a Git worktree of
that source. Do not put a private account id in the command.

`--checkout` defaults to that source project root. `--project` is the
Compose project name. The name MUST match `^[a-z0-9][a-z0-9_-]*$`.
The name MUST NOT start with a hyphen. The override file stays in the
source checkout. The launcher MUST resolve `--checkout`. The resolved
path MUST be the source checkout or a Git worktree that shares the
source git-common-dir. The launcher MUST reject any other directory.
The launcher MUST reject a subdirectory even when it contains
`compose.yaml`. The launcher MUST NOT copy tracked files.

The launcher validates an absolute credentials path. The path MUST
stay outside the selected checkout. The path MUST stay outside the
source checkout. The launcher MUST reject a symlink file. The
launcher MUST reject a symlink ancestor. The file MUST be a regular
file owned by the current user. The file and its parent MUST deny
group and other access. The launcher MUST remove every `AWS_*`
variable from the Compose process environment. The launcher MUST
remove `FEWIA_AWS_PROFILE`. The launcher MUST remove every
`FEWIA_BEDROCK_*` variable. The launcher sets
`FEWIA_RUNTIME_CREDENTIALS_FILE` to that absolute path. It MUST NOT
put secret values in the environment. The launcher MUST NOT copy host
AWS credentials or profiles into Compose. Git provenance queries MUST
use `git rev-parse` with an argument list. Those queries MUST NOT use
a shell. Those queries MUST clear `GIT_*` variables.

`compose.bedrock-runtime.yaml` binds that file read-only to
`/run/fewia/aws-credentials`. The bind sets `create_host_path: false`.
The override applies only to `api` and `worker`. It pins:

- `FEWIA_AWS_PROFILE=fewia-bedrock-runtime`
- `FEWIA_BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0`
- `FEWIA_BEDROCK_REGION=us-east-1`
- `AWS_SHARED_CREDENTIALS_FILE=/run/fewia/aws-credentials`
- `AWS_CONFIG_FILE=/dev/null`
- `AWS_EC2_METADATA_DISABLED=true`

Compose MUST NOT receive the admin profile. Compose MUST NOT set
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN`.

The coordinator verified these running Compose projects:

- `fewia-macros`: API 8011, web 5174
- `fewia-grocery-b7d4`: API 8010, web 5173

The launcher recreated `api` and `worker`. Nginx was reloaded.
Runtime host identity matched the CDK `UserArn`.
Four containers passed STS as that dedicated user.
Each container used the read-only credentials mount.
Those containers did not set `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, or `AWS_SESSION_TOKEN`.
Both provider endpoints `/api/grocery/providers` reported
`chat_configured` true.

The human MFA path stays `compose.bedrock.yaml`. Keep the host MFA
helper and profile `fewia-bedrock-dev` for that path. Leave
`FEWIA_BEDROCK_ROLE_ARN` and `FEWIA_BEDROCK_MFA_SERIAL` unused on the
unattended path.

Floci dummy credentials stay separate. Do not set a global
`AWS_ENDPOINT_URL`. Bedrock MUST keep the real regional
`bedrock-runtime` endpoint.

The host Docker engine and the application containers MUST stay
running for this path. This item does not create an automatic
development schedule.

Rotate or revoke the access key when it leaks or when the workload ends.
IAM access-key guidance:
[Managing access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html).

## Cost allocation

IAM principal tags can appear in Cost Explorer after Bedrock records
them. Attribution uses `iamPrincipal/Project` from tag `Project`.
See
[Bedrock IAM principal tracking](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-iam-principal-tracking.html).

The coordinator activated these six `iamPrincipal` keys and verified
them Active:

- `Project`
- `Environment`
- `Component`
- `ManagedBy`
- `Model`
- `ReasoningEffort`

Cost Explorer filter: `iamPrincipal/Project=FEWIA`.
Tag `CostCenter` is attached on the resources.
`CostCenter` is not yet registered for billing activation.
That optional dimension waits for AWS propagation.

This tagging is IAM principal attribution.
This project does not create an application inference profile.
See
[Cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html).

Operators MUST NOT claim current charges until Cost Explorer shows
them after AWS billing delay.
This stack does not set a spending cap.

## Teardown

Operators MUST deactivate the access key first.
Operators MUST delete the deactivated key.
Then destroy `FewiaBedrockRuntime` if the user authorizes that action.
The user resource remains because removal policy is `RETAIN`.
Operators MUST delete the retained user in IAM after the key is gone.

Do not destroy `FewiaBedrockDev` as part of this teardown.
Do not change the shared bootstrap role as part of this teardown.
Destroy `FewiaBedrockRuntimeDeployment` only after the user stack
teardown if the user authorizes that action. See `DEPLOYMENT.md`.

## Sources

- [Bedrock runtime CloudFormation execution role](DEPLOYMENT.md)
- [Bedrock IAM principal tracking](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-iam-principal-tracking.html)
- [Managing access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
- [IAM principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html)
- [Cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)
