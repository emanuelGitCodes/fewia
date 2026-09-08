# AWS request draft: Enable GPT-5.6 Luna access on Amazon Bedrock

Status: UNSENT.

This file is a reviewable draft. Operators MUST NOT send it until the
user authorizes that action. This worker did not send the request.

Source: coordinator checkpoint dated 2026-09-08. This file does not
claim independent live AWS checks.

Official contact:
https://aws.amazon.com/contact-us/sales-support/

## Subject

Enable GPT-5.6 Luna access on Amazon Bedrock

## Draft body

Account: 275452506840

Origin region: us-east-1

Model: `us.openai.gpt-5.6-luna`

API: Amazon Bedrock Converse

Reasoning effort: low

Project FEWIA is a local academic grocery planner. One developer tests
the application.

Please confirm whether this account is eligible to invoke
`us.openai.gpt-5.6-luna` through Converse. Enable the model if the
account is eligible. Identify any remaining requirement if it is not.

The coordinator reported these availability states. The admin identity
completed a one-time `create-foundation-model-agreement` for the
user-selected Luna model:

- agreement: AVAILABLE
- authorization: AUTHORIZED
- entitlement: AVAILABLE
- region: AVAILABLE
- US inference profile: ACTIVE

The agreement availability progressed from PENDING to AVAILABLE.

A later runtime Converse probe still returned this error:

```
AccessDeniedException: openai.gpt-5.6-luna is not available for this account, explore other models or contact AWS Sales
```

The same denial occurred for the restricted assumed role and for the
admin identity in this account. A propagation wait did not change the
result.

Please confirm eligibility. Enable the model, or name the remaining
requirement.

This draft contains no credentials, tokens, MFA codes, or offer tokens.
This draft contains no personal contact details.
This draft does not invent a support request ID.
