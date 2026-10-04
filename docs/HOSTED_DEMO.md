# Invitation-only hosted demo

This is a source runbook. No deployed evidence is recorded here.
The command templates do not authorize any action.
The owner MUST confirm each AWS mutation separately before the coordinator performs it.
The coordinator MUST NOT treat preflight success as owner confirmation.

## Access and product boundary

Follow [decision 0019](../wiki/decisions/0019-invitation-only-hosting.md).
Only the owner and invited users receive access.
An administrator creates Cognito users. Public signup stays disabled.
All invitees share one server-selected demo user and its application data.
Authentication provides no per-user data isolation.
The owner MUST explain this shared context before inviting each user.
Invitees MUST NOT enter private financial, health, or other sensitive information.

The local product uses React and TypeScript chat, FastAPI, PostgreSQL,
a worker, and Floci SQS and S3. Real Bedrock handles language interpretation
through `LLMProvider`. Application tools perform budget arithmetic and catalog validation.
The hosted path uses AWS SQS for queue transport instead of Floci.
The private S3 artifact bucket and adapter exist, but artifact export remains dormant.
Runtime task roles have no S3 grants. The hosted runtime does not actively use S3 artifacts.
The active stack runs one app service and one agent service.
The app task contains the API and web containers. No sync worker runs.

The accepted catalog contains 40 meals under decision 0017.
Requests accept one to three (1-3) meals and one to eight (1-8) servings per meal.
Manual budget defaults are USD 100 per month and a USD 40 plan cap.
Application tools MUST use USD integer cents for budget inputs and arithmetic.
The entered monthly limit remains the whole budget. These limits do not reserve money.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Plaid Sandbox remains paused. Live Instacart remains parked.
Instacart development shopping links provide a handoff only.
The demo MUST NOT submit purchases, orders, or payments or use real bank accounts.
Synthetic and sample data do not verify retailer, financial, or population claims.
Retired health and activity planning remains historical.
[Decision 0018](../wiki/decisions/0018-retain-legacy-data.md) retains legacy records.
This procedure does not authorize their deletion or reuse as current price evidence.

## Integration prerequisites

The hosting source, this runbook, and the preflight CLI are merged on `main`
at `ed00904` (2026-10-04). Two synth findings from the
[integrity check](../wiki/phases/integrity-20261004.md) MUST be fixed before
the first deployment: fixed availability zones on both stacks, and a non-root
nginx container on port 8080.

The coordinator MUST review and integrate the prerequisite branches and PRs:

- Network, database, retained resources, ECR assets, and execution and task roles.
- Cognito identity, task settings, app and worker task definitions, services, and HTTPS edge.
- AWS queue transport, verified database TLS, application-role bootstrap, and nginx task networking.
- Deployment configuration, `hosted_app.py`, bootstrap proof, and the preflight runner and CLI.

The coordinator MUST obtain explicit merge authorization for the source stack.
This runbook grants none. Record the integrated checkout SHA and review results in the wiki.
Build both images from that exact reviewed checkout.
The coordinator MUST run the changed-path gates and obtain independent Codex or Grok review.
The coordinator MUST validate all three examples against the final configuration loader.
The coordinator MUST check commands, output names, and links against the integrated sources.
The named integration snapshots establish the Dockerfile paths and build contexts in stage 2.
The named bootstrap proof source establishes the freshness window in stage 3.
The coordinator MUST compare these contracts with the final integrated sources before using these templates.

The deployment owner MUST supply these inputs:

- The actual 12-digit AWS account and deployment profile for `us-east-1`.
- A lowercase hostname under the owner's DNS control.
- An `ISSUED`, unexpired ACM certificate in that account and `us-east-1` matching the hostname.
- A unique available Cognito domain prefix, with 3-63 lowercase letters, digits, or hyphens.
- Permission to manage the hostname's DNS records and certificate validation records.
- Approval for the private shared demo context, cost exposure, and each separate AWS mutation.

The coordinator MUST check the certificate's trust chain separately using normal HTTPS validation.
A metadata match alone does not prove browser trust.
The environment needs AWS CLI v2, AWS CDK CLI, hosting Python dependencies,
Docker with Buildx, and Linux/amd64 build support.
The coordinator MUST verify tool and dependency versions against the integrated checkout.
The deployment profile MUST have only the reviewed permissions needed for each stage.
Use the owner's existing credential setup. Do not copy credentials into configuration or project records.
Real Bedrock access for `us.amazon.nova-2-lite-v1:0` needs separate live verification.

## Configuration and command conventions

The three [examples](../infra/hosting/examples/foundation.json) show configuration shape only:
[bootstrap](../infra/hosting/examples/bootstrap.json) and [active](../infra/hosting/examples/active.json).
They use synthetic account `123456789012`, hostname `demo.example.test`,
a placeholder Cognito prefix, a zero certificate UUID, and 64-hex placeholder digests.
They are NOT usable deployment configurations. Their syntax does not establish real resources.
The owner MUST replace every synthetic value in separate local configuration files.
The owner MUST NOT commit credentials or secret values.

Foundation accepts `account` and `phase`, with no runtime object.
Bootstrap and active require exactly these runtime fields:
`hostname`, `domain_prefix`, `certificate_arn`, `backend_digest`, and `frontend_digest`.
Both image digests have the form `sha256:` followed by 64 lowercase hex digits.
Bootstrap and active use identical runtime inputs; only their phase differs.
The stack name is `FewiaHostedDemoDev`. Its region is fixed to `us-east-1`.

Templates below assume a shell at the reviewed repository root.
Replace the visibly marked placeholders before use. No template executes through this document.
`HOSTING_PYTHON` names an interpreter with the integrated hosting dependencies installed.
`FOUNDATION_CONFIG`, `BOOTSTRAP_CONFIG`, and `ACTIVE_CONFIG` name owner-prepared local files.
Keep each phase's assembly in a separate local directory.

```bash
PROFILE='OWNER_SUPPLIED_PROFILE'
ACCOUNT='OWNER_SUPPLIED_12_DIGIT_ACCOUNT'
REGION='us-east-1'
STACK='FewiaHostedDemoDev'
HOSTNAME='OWNER_SUPPLIED_HOSTNAME'
HOSTING_PYTHON='OWNER_SUPPLIED_HOSTING_PYTHON_PATH'
FOUNDATION_CONFIG='OWNER_SUPPLIED_FOUNDATION_CONFIG_PATH'
BOOTSTRAP_CONFIG='OWNER_SUPPLIED_BOOTSTRAP_CONFIG_PATH'
ACTIVE_CONFIG='OWNER_SUPPLIED_ACTIVE_CONFIG_PATH'
FOUNDATION_ASSEMBLY='OWNER_SUPPLIED_FOUNDATION_ASSEMBLY_PATH'
BOOTSTRAP_ASSEMBLY='OWNER_SUPPLIED_BOOTSTRAP_ASSEMBLY_PATH'
ACTIVE_ASSEMBLY='OWNER_SUPPLIED_ACTIVE_ASSEMBLY_PATH'
```

Use `cdk synth` with the fixed executable app command shown in each phase.
The Toolkit resolves missing Availability Zone context, then reruns the Python app.
Synthesis can read AWS metadata and write local context and assembly data.
It does not deploy resources, run tasks, create users, or send invitations.
See the official [CDK context guide](https://docs.aws.amazon.com/cdk/v2/guide/context.html)
and [synth CLI reference](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-synth.html).
The coordinator MUST export the task-specific interpreter, configuration, and output variables shown below.
The coordinator MUST keep the app command string fixed, including its shell quotes.
The coordinator MUST NOT interpolate owner-supplied paths into the app shell text.
The coordinator MUST run all commands from the reviewed repository root.
CDK `--output` and Python `--outdir` use the same assembly directory for each phase.
Use the explicit profile and region even when a tool has defaults.
CDK commands below set the region through environment variables or the bootstrap target.
AWS CLI commands carry explicit `--profile` and `--region` arguments.

**OFFLINE / LOCAL READ:** define the assembly check in the same shell before using the phase commands.
Before every diff or deploy with a prebuilt assembly, the coordinator MUST require an empty manifest `missing` list.
An omitted `missing` field means no missing context.
The coordinator MUST verify that its template artifacts contain no `dummy1a`, `dummy1b`, or `dummy1c` placeholders.
The Python CLI's `synthesized` status alone does not meet this check.
The coordinator MUST stop if synthesis or the assembly check fails.

```bash
check_hosting_assembly() {
  "$HOSTING_PYTHON" - "$1" <<'PY'
import json
import sys
from pathlib import Path


def check_assembly(assembly: Path) -> None:
    manifest = json.loads((assembly / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("missing", []) != []:
        raise SystemExit("Assembly has unresolved context")
    templates = [
        artifact["properties"]["templateFile"]
        for artifact in manifest["artifacts"].values()
        if artifact["type"] == "aws:cloudformation:stack"
    ]
    if not templates:
        raise SystemExit("Assembly has no stack templates")
    for template_file in templates:
        template = (assembly / template_file).read_text(encoding="utf-8")
        if any(dummy in template for dummy in ("dummy1a", "dummy1b", "dummy1c")):
            raise SystemExit("Assembly has dummy Availability Zone placeholders")


check_assembly(Path(sys.argv[1]))
PY
}
```

`python infra/hosting/preflight_cli.py` performs fixed read-only AWS metadata calls.
Its allowlist is STS `get-caller-identity`, ACM `describe-certificate`,
CloudFormation `describe-stacks`, ECR `describe-images`, and ECS `describe-tasks`.
Foundation checks the caller account. Bootstrap adds certificate, stack, and image checks.
Active also checks the supplied bootstrap task ARN.
The CLI requires `--config` and `--profile`. It fixes AWS calls to `us-east-1`.
Only active accepts a bootstrap task ARN.

Preflight does not authorize deployment. It does not prove database contents,
secret rotation, scan cleanliness, image architecture, certificate trust chain,
authentication, or a live chat. Verify each separately.
The coordinator MUST stop on nonzero exit or a failed or interrupted status.
The coordinator MUST NOT retrieve or print Secrets Manager values.
Database secrets flow through ECS secret bindings only.
The bootstrap task binds both administrator and application secrets.
App and agent tasks bind only the application database password.

## Stage 1: foundation

**READ-ONLY AWS / LOCAL OUTPUT:** synthesize the foundation assembly through the Toolkit.

```bash
export HOSTING_SYNTH_PYTHON="$HOSTING_PYTHON"
export HOSTING_SYNTH_CONFIG="$FOUNDATION_CONFIG"
export HOSTING_SYNTH_OUTDIR="$FOUNDATION_ASSEMBLY"
AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk synth "$STACK" --profile "$PROFILE" --output "$HOSTING_SYNTH_OUTDIR" \
  --app 'exec "$HOSTING_SYNTH_PYTHON" "infra/hosting/hosted_app.py" --config "$HOSTING_SYNTH_CONFIG" --outdir "$HOSTING_SYNTH_OUTDIR"'
```

**READ-ONLY AWS:** confirm caller metadata and inspect the diff.
CDK diff MUST use `--no-change-set` to avoid creating a change set.
If CDK bootstrap resources are absent, complete the separately approved bootstrap first.

```bash
"$HOSTING_PYTHON" 'infra/hosting/preflight_cli.py' \
  --config "$FOUNDATION_CONFIG" --profile "$PROFILE"
check_hosting_assembly "$FOUNDATION_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$FOUNDATION_ASSEMBLY" --profile "$PROFILE" \
  diff "$STACK" --no-change-set
```

**MUTATING AWS — separate owner confirmation for CDK bootstrap, if needed:**

```bash
cdk bootstrap "aws://$ACCOUNT/$REGION" --profile "$PROFILE"
```

**MUTATING AWS — separate owner confirmation for foundation deployment:**

```bash
check_hosting_assembly "$FOUNDATION_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$FOUNDATION_ASSEMBLY" --profile "$PROFILE" \
  deploy "$STACK" --require-approval 'any-change'
```

Foundation creates the network, RDS, secrets, ECR repositories, and supporting resources.
Costs start here, before the app serves traffic. Foundation has no Cognito edge or services.
The coordinator MUST verify stack completion before continuing.

**READ-ONLY AWS:** obtain exact stack outputs. Do not substitute guessed names or IDs.

```bash
aws cloudformation describe-stacks --stack-name "$STACK" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager \
  --query 'Stacks[].{Status:StackStatus,Outputs:Outputs}' --output 'json'
```

Read `BackendRepositoryName`, `BackendRepositoryUri`, `FrontendRepositoryName`,
`FrontendRepositoryUri`, `ApplicationSubnetIds`, and `ApplicationSecurityGroupId`.
Record only nonsensitive deployment metadata. Do not record secret contents.

## Stage 2: build, push, and pin images

The coordinator MUST verify both Dockerfiles and build contexts in the reviewed integrated checkout.
The backend uses `backend/Dockerfile` with repository-root context `.`.
It copies backend files and `infra` from that root context.
The frontend uses `frontend/Dockerfile` with context `frontend`.
Its copy paths resolve within the frontend context.
The root `.dockerignore` excludes credentials and generated directories from the backend's root context.
Those root exclusions do not apply to the frontend context.
The coordinator MUST inspect the frontend context separately before building.
Use a unique tag tied to the reviewed SHA. Tags aid discovery; runtime configuration pins digests.

```bash
BUILD_TAG='OWNER_SUPPLIED_REVIEWED_SHA_TAG'
BACKEND_DOCKERFILE='backend/Dockerfile'
FRONTEND_DOCKERFILE='frontend/Dockerfile'
BACKEND_BUILD_CONTEXT='.'
FRONTEND_BUILD_CONTEXT='frontend'
BACKEND_REPOSITORY_NAME='EXACT_BACKEND_REPOSITORY_NAME_OUTPUT'
FRONTEND_REPOSITORY_NAME='EXACT_FRONTEND_REPOSITORY_NAME_OUTPUT'
BACKEND_REPOSITORY_URI='EXACT_BACKEND_REPOSITORY_URI_OUTPUT'
FRONTEND_REPOSITORY_URI='EXACT_FRONTEND_REPOSITORY_URI_OUTPUT'
ECR_REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
```

**OFFLINE / LOCAL OUTPUT:** build Linux/amd64 images and inspect their architecture.
Builds can read dependency registries. They do not mutate AWS resources.

```bash
docker buildx build --platform 'linux/amd64' --load \
  --file "$BACKEND_DOCKERFILE" --tag "$BACKEND_REPOSITORY_URI:$BUILD_TAG" \
  "$BACKEND_BUILD_CONTEXT"
docker buildx build --platform 'linux/amd64' --load \
  --file "$FRONTEND_DOCKERFILE" --tag "$FRONTEND_REPOSITORY_URI:$BUILD_TAG" \
  "$FRONTEND_BUILD_CONTEXT"
docker image inspect --format '{{.Os}}/{{.Architecture}}' \
  "$BACKEND_REPOSITORY_URI:$BUILD_TAG" "$FRONTEND_REPOSITORY_URI:$BUILD_TAG"
```

**READ-ONLY AWS / LOCAL AUTHENTICATION:** authenticate Docker through standard input.
The ECR authorization token feeds Docker only. Do not print or store it in project records.
Use the owner's approved Docker credential storage. Disable shell tracing for authentication.

```bash
aws ecr get-login-password --profile "$PROFILE" --region "$REGION" \
  | docker login --username 'AWS' --password-stdin "$ECR_REGISTRY"
```

**MUTATING AWS — separate owner confirmation for each image push:**

```bash
docker push "$BACKEND_REPOSITORY_URI:$BUILD_TAG"
```

Obtain a new owner confirmation before the frontend push.

```bash
docker push "$FRONTEND_REPOSITORY_URI:$BUILD_TAG"
```

Docker push uses the authenticated account and region in each exact repository URI.
The coordinator MUST check those URIs against the account and foundation outputs before each push.

**READ-ONLY AWS:** read exact image digests after both pushes.

```bash
aws ecr describe-images --registry-id "$ACCOUNT" \
  --repository-name "$BACKEND_REPOSITORY_NAME" --image-ids "imageTag=$BUILD_TAG" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager \
  --query 'imageDetails[].{Digest:imageDigest,PushedAt:imagePushedAt}' --output 'json'
aws ecr describe-images --registry-id "$ACCOUNT" \
  --repository-name "$FRONTEND_REPOSITORY_NAME" --image-ids "imageTag=$BUILD_TAG" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager \
  --query 'imageDetails[].{Digest:imageDigest,PushedAt:imagePushedAt}' --output 'json'
```

The coordinator MUST require one matching image per repository.
Put those exact digests into both runtime configurations.
The coordinator MUST verify image architecture and scan results separately.
Image existence does not establish either property.

## Stage 3: bootstrap infrastructure with services at zero

**READ-ONLY AWS / LOCAL OUTPUT:** synthesize the bootstrap assembly through the Toolkit from the pinned configuration.

```bash
export HOSTING_SYNTH_PYTHON="$HOSTING_PYTHON"
export HOSTING_SYNTH_CONFIG="$BOOTSTRAP_CONFIG"
export HOSTING_SYNTH_OUTDIR="$BOOTSTRAP_ASSEMBLY"
AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk synth "$STACK" --profile "$PROFILE" --output "$HOSTING_SYNTH_OUTDIR" \
  --app 'exec "$HOSTING_SYNTH_PYTHON" "infra/hosting/hosted_app.py" --config "$HOSTING_SYNTH_CONFIG" --outdir "$HOSTING_SYNTH_OUTDIR"'
```

**READ-ONLY AWS:** check metadata and the bootstrap diff.

```bash
"$HOSTING_PYTHON" 'infra/hosting/preflight_cli.py' \
  --config "$BOOTSTRAP_CONFIG" --profile "$PROFILE"
check_hosting_assembly "$BOOTSTRAP_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$BOOTSTRAP_ASSEMBLY" --profile "$PROFILE" \
  diff "$STACK" --no-change-set
```

**MUTATING AWS — separate owner confirmation for bootstrap-phase deployment:**

```bash
check_hosting_assembly "$BOOTSTRAP_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$BOOTSTRAP_ASSEMBLY" --profile "$PROFILE" \
  deploy "$STACK" --require-approval 'any-change'
```

This phase creates Cognito, the HTTPS ALB, task definitions, and two services.
Both services have desired count zero. No sync service is created.
The bootstrap task runs `python -m app.bootstrap_hosting --run` from its task definition.
It prepares the dedicated database and application-role permissions.
It uses `fewia_admin` for bootstrap and `fewia_app` for normal runtime access.

**READ-ONLY AWS:** repeat `describe-stacks` from stage 1 after stack completion.
Use its exact `ClusterArn`, `BootstrapTaskDefinitionArn`, `ApplicationSubnetIds`,
and `ApplicationSecurityGroupId` for the one-shot task.
Also retain `AppServiceName`, `AgentServiceName`, `LoadBalancerDnsName`,
`LoadBalancerHostedZoneId`, `UserPoolId`, and `DemoUrl` for later checks.

```bash
CLUSTER_ARN='EXACT_CLUSTER_ARN_OUTPUT'
BOOTSTRAP_TASK_DEFINITION_ARN='EXACT_BOOTSTRAP_TASK_DEFINITION_ARN_OUTPUT'
APPLICATION_SUBNET_IDS='EXACT_COMMA_SEPARATED_APPLICATION_SUBNET_IDS_OUTPUT'
APPLICATION_SECURITY_GROUP_ID='EXACT_APPLICATION_SECURITY_GROUP_ID_OUTPUT'
BOOTSTRAP_CLIENT_TOKEN='OWNER_SUPPLIED_UNIQUE_TOKEN_FOR_THIS_RUN'
```

The coordinator MUST confirm these are the stack's private application subnets and security group.
The coordinator MUST keep `assignPublicIp=DISABLED`.
The coordinator MUST NOT supply command, role, environment, secret, or other task overrides.
The task definition carries all runtime configuration and ECS secret bindings.

**MUTATING AWS — separate owner confirmation for this one-shot bootstrap task:**

```bash
aws ecs run-task --cluster "$CLUSTER_ARN" \
  --task-definition "$BOOTSTRAP_TASK_DEFINITION_ARN" \
  --launch-type 'FARGATE' --platform-version '1.4.0' --count '1' \
  --client-token "$BOOTSTRAP_CLIENT_TOKEN" \
  --network-configuration "awsvpcConfiguration={subnets=[$APPLICATION_SUBNET_IDS],securityGroups=[$APPLICATION_SECURITY_GROUP_ID],assignPublicIp=DISABLED}" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager --output 'json'
```

The coordinator MUST require exactly one result in `tasks` and an empty `failures` list.
Copy that result's exact task ARN. A returned ARN alone does not prove bootstrap completion.
If the response is missing or uncertain, stop. Reconcile task state through read-only metadata.
The coordinator MUST NOT repeat an uncertain mutation or silently launch a replacement task.

```bash
BOOTSTRAP_TASK_ARN='EXACT_ARN_FROM_THE_SINGLE_RUN_TASK_RESULT'
```

**READ-ONLY AWS:** wait for `STOPPED`, then inspect completion metadata.

```bash
aws ecs wait tasks-stopped --cluster "$CLUSTER_ARN" --tasks "$BOOTSTRAP_TASK_ARN" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager
aws ecs describe-tasks --cluster "$CLUSTER_ARN" --tasks "$BOOTSTRAP_TASK_ARN" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager --output 'json' \
  --query '{Failures:failures,Tasks:tasks[].{Arn:taskArn,Definition:taskDefinitionArn,Status:lastStatus,StoppedAt:stoppedAt,Containers:containers[].{Name:name,Digest:imageDigest,ExitCode:exitCode}}}'
"$HOSTING_PYTHON" 'infra/hosting/preflight_cli.py' \
  --config "$ACTIVE_CONFIG" --profile "$PROFILE" \
  --bootstrap-task-arn "$BOOTSTRAP_TASK_ARN"
```

Active preflight can check the completed task while the deployed phase is still bootstrap.
The coordinator MUST verify the exact task ARN and cluster ARN through active preflight.
The coordinator MUST verify the exact current task-definition revision and no behavior-changing overrides.
The coordinator MUST verify bootstrap exit code zero and the pinned backend digest.
`check_bootstrap_task` requires a supplied timezone-aware `now`.
The coordinator MUST verify `startedAt <= stoppedAt <= now`.
The coordinator MUST verify that `stoppedAt` falls within the previous 24 hours, including the boundary.
The exact window is `now - stoppedAt <= timedelta(hours=24)`; future completion timestamps fail.
Preflight success proves metadata checks only. It does not prove database contents or secret rotation.
The coordinator MUST verify the expected bootstrap result and database access separately without exposing secrets.
After a secret rotation or task-definition revision change, obtain new owner confirmation for explicit bootstrap.
The coordinator MUST run and verify that bootstrap again before enabling services.

## Stage 4: activate the app and agent

The coordinator MUST finish stage 3 and separate verification before activation.
Keep the same hostname, certificate, Cognito prefix, and image digests in the active configuration.
If any bootstrap input changes, stop and review the bootstrap requirements again.

**READ-ONLY AWS / LOCAL OUTPUT:** synthesize the active assembly through the Toolkit.

```bash
export HOSTING_SYNTH_PYTHON="$HOSTING_PYTHON"
export HOSTING_SYNTH_CONFIG="$ACTIVE_CONFIG"
export HOSTING_SYNTH_OUTDIR="$ACTIVE_ASSEMBLY"
AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk synth "$STACK" --profile "$PROFILE" --output "$HOSTING_SYNTH_OUTDIR" \
  --app 'exec "$HOSTING_SYNTH_PYTHON" "infra/hosting/hosted_app.py" --config "$HOSTING_SYNTH_CONFIG" --outdir "$HOSTING_SYNTH_OUTDIR"'
```

**READ-ONLY AWS:** repeat active preflight immediately before deployment and inspect the diff.

```bash
"$HOSTING_PYTHON" 'infra/hosting/preflight_cli.py' \
  --config "$ACTIVE_CONFIG" --profile "$PROFILE" \
  --bootstrap-task-arn "$BOOTSTRAP_TASK_ARN"
check_hosting_assembly "$ACTIVE_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$ACTIVE_ASSEMBLY" --profile "$PROFILE" \
  diff "$STACK" --no-change-set
```

**MUTATING AWS — separate owner confirmation for active deployment:**

```bash
check_hosting_assembly "$ACTIVE_ASSEMBLY" && \
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" \
  cdk --app "$ACTIVE_ASSEMBLY" --profile "$PROFILE" \
  deploy "$STACK" --require-approval 'any-change'
```

Active enables one app service task and one agent service task.
Deployment replacement can temporarily overlap tasks. Sync stays absent.
The coordinator MUST verify stable services, task digests, and healthy ALB targets separately.
Repeat stack-output retrieval and active preflight after deployment.

## Stage 5: DNS, access, and live acceptance

The owner chooses the hostname. Map it to the exact ALB output.
Use an alias with `LoadBalancerDnsName` and `LoadBalancerHostedZoneId` where the DNS provider supports it.
A subdomain CNAME MAY target `LoadBalancerDnsName` where the DNS provider supports it.
DNS provider inputs vary. The coordinator MUST prepare a concrete record change for owner review.
**MUTATING AWS or DNS — obtain separate owner confirmation before applying that record change.**
Certificate requests and validation record changes also need separate owner confirmation.
This runbook does not create or select a certificate.

For Route 53, use the owner's zone ID and a separately reviewed change-batch file.
That file names the chosen hostname and exact ALB alias target outputs.
The coordinator MUST review its record name, type, target, and action before requesting confirmation.

```bash
DNS_ZONE_ID='OWNER_SUPPLIED_ROUTE53_ZONE_ID'
DNS_CHANGE_FILE='OWNER_REVIEWED_DNS_CHANGE_JSON_PATH'
```

**MUTATING AWS — separate owner confirmation for this exact DNS change:**

```bash
aws route53 change-resource-record-sets --hosted-zone-id "$DNS_ZONE_ID" \
  --change-batch "file://$DNS_CHANGE_FILE" \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager --output 'json'
```

For another DNS provider, return its concrete record change to the owner for separate confirmation.

Administrator-only user creation MUST keep public signup disabled.
User creation and invitation delivery each need a separate explicit owner confirmation.
The coordinator MUST NOT send an invitation without an explicit instruction to send it.
The owner MUST explain the shared demo context to each invitee before sending an invitation.
Prepare the exact user and delivery action for review without recording passwords or tokens.
An administrator MAY create a user with delivery suppressed, then send a separately approved invitation.
Do not treat a suppressed invitation as a usable login or a sent invitation.

Use the exact stack `UserPoolId` and the owner-approved invitee email.
Keep invitee details outside source and evidence records.
These templates supply no password, token, or secret value.

```bash
USER_POOL_ID='EXACT_USER_POOL_ID_OUTPUT'
INVITEE_EMAIL='OWNER_APPROVED_INVITEE_EMAIL'
```

**MUTATING AWS — separate owner confirmation for user creation with delivery suppressed:**

```bash
aws cognito-idp admin-create-user --user-pool-id "$USER_POOL_ID" \
  --username "$INVITEE_EMAIL" --user-attributes "Name=email,Value=$INVITEE_EMAIL" \
  --message-action 'SUPPRESS' --desired-delivery-mediums 'EMAIL' \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager \
  --query 'User.UserStatus' --output 'json'
```

**MUTATING AWS — separate explicit instruction and owner confirmation to send this invitation:**

```bash
aws cognito-idp admin-create-user --user-pool-id "$USER_POOL_ID" \
  --username "$INVITEE_EMAIL" --message-action 'RESEND' \
  --desired-delivery-mediums 'EMAIL' \
  --profile "$PROFILE" --region "$REGION" --no-cli-pager \
  --query 'User.UserStatus' --output 'json'
```

`RESEND` sends an invitation for the existing user and resets the temporary-password validity period.
The coordinator MUST verify delivery and first login separately without collecting the invitee's password.
If either operation has an uncertain result, inspect state before proposing another mutation.

The coordinator MUST observe these acceptance checks before recording deployed success:

- The chosen hostname resolves to the ALB. Normal HTTPS validation passes without a trust bypass.
- Anonymous requests to the chosen host redirect to authentication before reaching the app or API.
- A request with a wrong Host header receives the listener's fixed 404 response.
- The ALB has no HTTP port 80 listener. The public edge exposes HTTPS only.
- The API has no public bypass. Tasks have no public IPs. RDS is not public.
- Private subnet and security group controls match the reviewed design.
- Cognito has no public signup. An approved invited account can log in.
- Logged-in chat completes a real Bedrock request through the agent worker.
- The owner confirms each invitee received the shared demo context explanation before invitation delivery.
- Manual budget defaults, meal limits, serving limits, and catalog validation match the accepted product scope.
- Budget inputs and arithmetic use USD integer cents. The entered monthly limit remains the whole budget.
  Available budget equals the monthly limit minus net posted grocery spending, with a zero floor.
  A smaller explicit plan cap limits the available plan budget. Pending spending appears separately.
- Each displayed grocery estimate includes the exact sample-price notice above.
- Instacart development links remain a handoff. Plaid, live Instacart, and the sync worker remain parked.

The internal ALB target port 80 does not create a public HTTP listener.
For a wrong-host probe, use valid TLS for the chosen hostname and change only the HTTP Host header.
The coordinator MUST NOT disable certificate validation to obtain a passing probe.
Live chat submits a job and incurs Bedrock usage. Obtain owner confirmation before that acceptance action.
Do not include personal data, credentials, or secret values in probes or evidence.

## Stop, restore, and rollback without data deletion

Every rollback, service change, secret rotation, DNS reversal, or deletion needs separate owner confirmation.
First inspect the current stack, services, task state, and retained resources through read-only metadata.
The coordinator MUST resolve any uncertain prior action before proposing another mutation.

To stop application work, propose the reviewed bootstrap configuration with both desired counts at zero.
Use its synthesis and `diff --no-change-set` steps before asking the owner to approve deployment.
Scaling services to zero does not stop NAT, RDS, or ALB charges.
Running one-shot tasks also need inspection; service scaling does not stop them.
Do not return an existing runtime stack to foundation merely to stop services.
That phase omits identity and edge resources and can propose destructive changes.

To restore, use the last reviewed runtime configuration and pinned image digests.
Review the diff and current task-definition revision.
Run a newly approved bootstrap after secret rotation or revision changes.
Repeat active preflight and separate acceptance checks before claiming restoration.
Application rollback does not authorize a schema downgrade or data deletion.

Retain RDS, administrator and application secrets, ECR repositories, and the S3 bucket.
Retain legacy data under decision 0018.
The stack has termination protection; RDS, ALB, and Cognito have deletion protections in source.
The coordinator MUST review each protection before proposing any removal.
The owner MUST approve any protection change separately from resource deletion.
Deletion requires a separate retention and backup review. Do not run `cdk destroy` as routine rollback.
Retained resources can continue to incur charges after stack deletion.

## Illustrative fixed pricing inputs

The saved pricing inputs give a fixed list-price subtotal of **USD 110.245392 for 730 hours**.
This is NOT a full quote or bill. It is not observed account usage.
The inputs assume `us-east-1`, no free tier, no discounts, and continuous resources for 730 hours.

| Fixed component | Exact assumed rate and quantity | USD subtotal |
| --- | --- | ---: |
| Fargate Linux X86 | Two tasks; each 0.5 vCPU and 1 GiB; 730 hours | 36.040392 |
| Standard NAT gateway | USD 0.045/hour; one gateway; 730 hours | 32.85 |
| Public IPv4 | USD 0.005/address-hour; three addresses; 2,190 address-hours | 10.95 |
| ALB hours | USD 0.0225/hour; one ALB; 730 hours | 16.425 |
| RDS PostgreSQL Single-AZ db.t4g.micro | USD 0.016/hour; 730 hours | 11.68 |
| RDS Single-AZ GP3 | USD 0.115/GB-month; 20 GB | 2.30 |

Fargate uses USD 0.000011244/vCPU-second and USD 0.000001235/GB-second.
Its calculation is `2 * (0.5 * 0.000011244 + 1 * 0.000001235) * 730 * 3600`.
The three assumed IPv4 addresses are two for the ALB and one for the NAT gateway.
Actual address allocation and usage can differ.

Primary official sources are [Fargate pricing](https://aws.amazon.com/fargate/pricing/),
[VPC pricing](https://aws.amazon.com/vpc/pricing/),
[ALB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/), and
[RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/).
The saved inputs also name official price maps for
[NAT](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/natgateway.json),
[IPv4](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/vpc/USD/current/vpc.json),
[ALB](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/elb/USD/current/elb.json), and
[RDS](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/rds/USD/current/rds-postgresql-ondemand.json).
These links can change. Preserve the saved inputs as the provenance for this subtotal.

The subtotal excludes ALB LCUs, NAT data processing, RDS burst credits,
backup growth, storage growth, and retained resources after stack deletion.
It also excludes CloudWatch, Secrets Manager, Bedrock, SQS, S3, ECR, Cognito,
data transfer, domain costs, DNS, tax, temporary bootstrap tasks, and overlapping deployment tasks.
Foundation starts costs before activation. Zero service tasks do not mean zero cost.

## Evidence and handoff

| Evidence class | What it supports | What it does not establish |
| --- | --- | --- |
| Source | Reviewed configuration, command contracts, and saved pricing inputs | Deployment or live behavior |
| Deterministic | Offline parsing, synthesis, tests, and local Floci observations when actually run | Real AWS, retailer, or bank behavior |
| Sandbox | Observed Plaid Sandbox or development shopping-link behavior | Real bank data, retailer prices, purchases, or payments |
| Live | Observed real Bedrock response or normal HTTPS behavior | Unobserved deployment controls or per-user isolation |
| Deployed | Observed controls and behavior for a named deployed revision | Other revisions, future state, or verified retailer and financial claims |

The foundation, bootstrap, and active CDK synth commands were checked with cached synthetic Availability Zone context and `--lookups=false`.
These checks provide deterministic local synthesis evidence.
They used no AWS credentials, live context lookup, AWS mutation, or deployment.
The `--lookups=false` flag and cached synthetic context describe the offline probe only.
The future synthesis commands above can perform read-only AWS context lookups.
This source runbook remains undeployed. No deployed acceptance evidence is recorded.
The coordinator MUST keep gates, independent review, CI, merge, and deployment evidence separate.
Record deployed evidence only after direct observation.
Use append-only wiki entries with the checkout SHA, configuration phase, image digests,
task-definition revision, bootstrap task ARN, observation time, evidence class, and limitations.
Record the exact pricing inputs and primary citations with any cost table.
Exclude credentials, secret values, login tokens, and invitee personal data from records.

The writer leaves JSON parser validation, command and link checks, gates,
independent review, source integration, and all external actions to the coordinator.
The coordinator MUST compare the documented build inputs and bootstrap proof rules with the final integrated sources before deployment.
The owner still supplies account, profile, hostname, certificate, DNS control, and action confirmations.
