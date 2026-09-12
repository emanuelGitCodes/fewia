# Bedrock runtime CloudFormation execution role

This slice defines a separate Python CDK stack. The stack creates one IAM
role. CloudFormation assumes that role when it deploys
`FewiaBedrockRuntime`. The role manages one named IAM user. The role does
not invoke a model. The role does not create access keys.

The current human-MFA stack `FewiaBedrockDev` MUST remain unchanged.
Operators MUST NOT change the shared CDK bootstrap role or its policies.

This slice does not claim a deploy. Status stays planned until the
coordinator verifies the live stacks.

## Boundary

Operators MUST synthesize this stack through `deployment_app.py`.
That entrypoint instantiates `FewiaBedrockRuntimeDeployment` only.
It MUST NOT instantiate `FewiaBedrockRuntime`.
It MUST NOT instantiate `FewiaBedrockDev`.
It uses the default CDK synthesizer. The default synthesizer uses the
existing bootstrap CloudFormation execution role.

```bash
cd infra/bedrock
cdk synth --app "python3 deployment_app.py" \
  -c account=111122223333 \
  -c region=us-east-1
```

Replace the synthetic account with the 12-digit target account at deploy
time. Do not commit a real account id.

Operators MUST NOT run `cdk bootstrap` or `cdk deploy` unless the user
authorizes that action. User-authorized deploy creates the execution
role. It does not create the runtime user. It does not prove Nova 2 Lite
invocation.

Context keys:

| Key | Rule |
|---|---|
| `account` | Exact 12-digit AWS account id |
| `region` | `us-east-1` |

Synth MUST fail when those values are missing or inexact.

## Identity

The stack creates IAM role `fewia-bedrock-runtime-deployment`.
CloudFormation is the only trusted service principal. The trust service
is `cloudformation.amazonaws.com`.

The inline policy lives on the role. Installed CDK supports
`inline_policies` on `iam.Role`. The policy grants these actions only,
on `arn:aws:iam::<account>:user/fewia/fewia-bedrock-runtime`:

- `iam:CreateUser`
- `iam:DeleteUser`
- `iam:GetUser`
- `iam:UpdateUser`
- `iam:TagUser`
- `iam:UntagUser`
- `iam:ListUserTags`
- `iam:PutUserPolicy`
- `iam:GetUserPolicy`
- `iam:DeleteUserPolicy`
- `iam:ListUserPolicies`
- `iam:ListGroupsForUser`
- `iam:ListAttachedUserPolicies`
- `iam:GetLoginProfile`

The identity MUST NOT receive wildcard actions or wildcard resources.
The identity MUST NOT receive access-key actions.
The identity MUST NOT receive `iam:CreateLoginProfile`,
`iam:UpdateLoginProfile`, or `iam:DeleteLoginProfile`.
The identity MUST NOT receive `iam:AddUserToGroup` or
`iam:RemoveUserFromGroup`.
The identity MUST NOT receive `iam:AttachUserPolicy` or
`iam:DetachUserPolicy`.
The identity MUST NOT receive Bedrock, S3, or STS data-plane actions.

CloudFormation uses `iam:GetLoginProfile`, `iam:ListGroupsForUser`,
and `iam:ListAttachedUserPolicies` to inspect user metadata.
The role does not set a password.
The role does not change group membership.
The role does not attach a managed policy.
The role does not detach a managed policy.

The coordinator MUST update the deployed role after review.

The role resource uses removal policy `RETAIN`. Stack delete does not
remove the role. Operators MUST manage that retained role explicitly.

The only stack output is `DeploymentRoleArn`. Outputs MUST NOT include
keys, secrets, or the runtime user.

Tags on the role:

- `Project=FEWIA`
- `Environment=development`
- `Component=bedrock-deployment`
- `ManagedBy=AWS-CDK`
- `Model=amazon.nova-2-lite-v1:0`
- `ReasoningEffort=low`
- `CostCenter=FEWIA`

## Deploy order

Operators MUST deploy `FewiaBedrockRuntimeDeployment` first.
The shared bootstrap CloudFormation execution role can create IAM roles.
That shared role has no IAM user actions. Operators MUST NOT widen it.

Operators MUST then deploy `FewiaBedrockRuntime` through
`workload_app.py`. The stack name stays `FewiaBedrockRuntime`.
`workload_app.py` selects `DefaultStackSynthesizer` with an empty
`deploy_role_arn` and with `cloud_formation_execution_role` set to
`arn:aws:iam::<account>:role/fewia-bedrock-runtime-deployment`.

Empty `deploy_role_arn` selects the CLI caller to submit CloudFormation.
The CLI caller MUST be the chosen aws-admin identity. The synthesizer
reuses the existing bootstrap template asset bucket and file publisher.
It MUST NOT create a bucket. Operators MUST NOT pass `--role-arn`.

```bash
cd infra/bedrock
cdk synth --app "python3 workload_app.py" \
  -c account=111122223333 \
  -c region=us-east-1
```

Replace the synthetic account with the 12-digit target account at deploy
time. Do not commit a real account id.

User-authorized deploy of `FewiaBedrockRuntime` creates the restricted
user. It does not prove Nova 2 Lite invocation. Access-key creation stays
with the coordinator after user authorization. See `UNATTENDED.md`.

## Teardown

Destroy `FewiaBedrockRuntime` only after the coordinator deactivates and
deletes the access key. The user resource remains because removal policy
is `RETAIN`. Then destroy `FewiaBedrockRuntimeDeployment` if the user
authorizes that action. The execution role remains because removal
policy is `RETAIN`. Operators MUST delete retained IAM resources in IAM.

Do not destroy `FewiaBedrockDev` as part of this teardown.
Do not change the shared bootstrap stack as part of this teardown.
