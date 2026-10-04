# 0019 — Invitation-only hosted demo

- Date: 2026-10-03 (America/New_York).
- Status: accepted access scope; implementation and deployment remain in progress.
- Relates to: [0018 — Retain legacy data](0018-retain-legacy-data.md),
  [project scope](../../.codex/project-context.md), and
  [hosting preparation](../phases/hosting-preparation-20261003.md).

## Decision

The hosted demo admits the owner and invited users only.
The hosted demo MUST NOT permit public signup.
The current application keeps one server-selected demo user.
Invited users share that demo context. They do not receive private application accounts.
Access authentication does not establish per-user data isolation.
The owner MUST explain the shared context before inviting users.

This decision accepts the access boundary. It does not report a deployed control.
The owner MUST confirm every mutating AWS step before the coordinator performs it.
That rule includes resource creation, user creation, and invitations.
No AWS resources, users, or invitations have been created by this run.
No merge authorization exists.

## Proposed design

An authenticated HTTPS edge uses Cognito users created by an administrator.
Cognito self-registration stays disabled. ECS Fargate tasks remain private.
RDS PostgreSQL uses isolated subnets, retention, and verified TLS.
Administrator and application credentials use separate Secrets Manager secrets.
Execution and application roles grant only the permissions each task needs.
CloudWatch holds task logs. Real Bedrock calls use the `LLMProvider` boundary.
This design is source preparation, not proof of deployed authentication or isolation.

The demo uses manual budgets. Proposed defaults are USD 100 per month and a USD 40 plan cap.
The user-entered monthly limit remains the whole budget under decision 0016.
The defaults do not verify financial data or reserve money.
Plaid Sandbox work remains paused. Live Instacart remains parked.
Instacart development shopping links retain their handoff-only evidence boundary.
The demo MUST NOT submit purchases, orders, or payments or use real bank accounts.

## Product boundary

The local product remains React and TypeScript chat, FastAPI, PostgreSQL,
a worker, and Floci SQS and S3. Real Bedrock supplies language interpretation.
Application tools own budget arithmetic and catalog validation.
The accepted catalog contains 40 meals under decision 0017.
Requests support one to three (1-3) meals and one to eight (1-8) servings per meal.
Every grocery estimate MUST show this exact notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

Retired health and activity planning stays historical.
Decision 0018 retains legacy records; this decision does not authorize their deletion.
Sample prices and synthetic data do not verify retailer, financial, or population claims.

## Implementation and deployment status

The [phase snapshot](../phases/hosting-preparation-20261003.md) records published source and bounded CI observations.
Runtime roles at `573dd0b` and identity at `14dd9e41` remain source checkpoints pending publication and review.
ECS task definitions, services, listeners, and stack composition remain in progress.
Application-role bootstrap, the deployment runbook, and preflight remain in progress.
The hostname, ACM certificate, and deployment credentials await owner input.
The coordinator MUST NOT invent these values or include credentials in project records.
The live hosted demo remains unverified.

The coordinator MUST keep local checks, independent review, CI, merge, and deployment evidence separate.
The coordinator MUST obtain merge authorization before merging a stack.
The coordinator MUST obtain owner confirmation before each mutating AWS step.
