# 0001 — Real Bedrock from day one

- **Date**: 2026-08-31
- **Status**: accepted

## Decision

The agent loop calls real Amazon Bedrock from the first implementation.
Floci serves only AWS-shaped integration tests (SQS, EventBridge, S3,
Secrets Manager). Floci MUST NOT stand in for the LLM.

## Options considered

1. Real Bedrock from day one — chosen.
2. Floci Bedrock stub first, swap later.
3. Claude API instead of Bedrock.

## Reason

The Floci stub returns canned responses, which hide real tool-calling
bugs. The AWS account is already connected. The course documents
describe Bedrock.

## Consequences

- Bedrock calls cost money during development. A fake `LLMProvider`
  keeps the test suite free and deterministic.
- aws-infra must confirm Bedrock model access before Phase 5.

Related: [0002](0002-frontend-after-mvp-checkpoint.md),
[phase 0](../phases/phase-0.md).
