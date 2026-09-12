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

This slice does not claim a deploy. This slice does not claim invocation.
This slice does not claim live cost proof.

## Boundary

Operators MUST synthesize this stack through `workload_app.py`.
That entrypoint instantiates `FewiaBedrockRuntime` only.
It MUST NOT instantiate `FewiaBedrockDev`.

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
user. It does not prove Nova 2 Lite invocation.

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

Outputs are `UserArn` and `UserName` only. Outputs MUST NOT include keys.

Tags on the stack and the user:

- `Project=FEWIA`
- `Environment=development`
- `Component=bedrock-chat`
- `ManagedBy=AWS-CDK`
- `Model=amazon.nova-2-lite-v1:0`
- `ReasoningEffort=low`
- `CostCenter=FEWIA`

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

Operators MUST start the base Compose services first. Run the
validated launcher from the source checkout. That checkout owns
`infra/bedrock_runtime.py` and `compose.bedrock-runtime.yaml`.

```bash
python -m infra.bedrock_runtime --checkout /path/to/fewia --project <compose-project>
```

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

The human MFA path stays `compose.bedrock.yaml`. Keep the host MFA
helper and profile `fewia-bedrock-dev` for that path. Leave
`FEWIA_BEDROCK_ROLE_ARN` and `FEWIA_BEDROCK_MFA_SERIAL` unused on the
unattended path.

Floci dummy credentials stay separate. Do not set a global
`AWS_ENDPOINT_URL`. Bedrock MUST keep the real regional
`bedrock-runtime` endpoint.

Rotate or revoke the access key when it leaks or when the workload ends.
IAM access-key guidance:
[Managing access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html).

## Cost allocation

IAM principal tags can appear in Cost Explorer after Bedrock records
them. Attribution uses `iamPrincipal/Project` from tag `Project`.
See
[Bedrock IAM principal tracking](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-iam-principal-tracking.html).

Operators MUST activate the principal tag in Billing after the first
Bedrock call. Tag appearance MAY take 24 hours. Activation MAY take
another 24 hours. Do not claim cost is visible until Cost Explorer
shows the tag after activation.

This stack does not set a spending cap. This stack does not prove
current charges.

## Teardown

Operators MUST deactivate the access key first.
Operators MUST delete the deactivated key.
Then destroy `FewiaBedrockRuntime` if the user authorizes that action.
The user resource remains because removal policy is `RETAIN`.
Operators MUST delete the retained user in IAM after the key is gone.

Do not destroy `FewiaBedrockDev` as part of this teardown.

## Sources

- [Bedrock IAM principal tracking](https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-iam-principal-tracking.html)
- [Managing access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
- [IAM principal cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html)
