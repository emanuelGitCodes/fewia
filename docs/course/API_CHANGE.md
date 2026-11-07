# Provider change record

This file holds facts and source pointers only. It contains no paper text.

## What changed

| Provider | Course sign-up sheet | Today | Source |
|---|---|---|---|
| Instacart | Listed | Retired. The frozen suite keeps a fixture handoff scenario, P02. | [decision 0023](../../wiki/decisions/0023-retire-instacart-adapter.md) |
| Withings | Listed | Not in the code path. No file in `backend/app` or `frontend/src` names it. | code search on 2026-11-07 |
| Plaid | Listed | Paused. The budget starts from a user-entered amount. No Sandbox run is archived. | [limitations](LIMITATIONS.md) |
| Kroger | Not listed | Store search, read-time price, cart preview, and a cart add that the user clicks. | [decision 0023](../../wiki/decisions/0023-retire-instacart-adapter.md), [feature map](../FEATURE_MAP.md) |
| Amazon Bedrock | Not a sheet column | Nova 2 Lite behind `LLMProvider`. | [evaluation](../EVALUATION.md) |

## Owner action

The owner MUST confirm the Kroger change with the professor, or state the change in the presentation. This repository holds no record of that confirmation.

## What the use case adds over the provider APIs

Each row names code that a provider API does not supply.

| Capability | Code |
|---|---|
| A deterministic planner sets every price and every total. The model sets none. | `backend/app/agent/planning_tool.py` |
| A validator checks model prose against tool results, and a template replaces rejected prose. | `backend/app/agent/grounding.py` |
| A plan change is a proposal. The user applies it. | `backend/app/agent/proposal_tool.py` |
| The agent stops before payment. The user clicks the cart add and checks out on kroger.com. | `backend/app/api/kroger.py`, `frontend/src/prototype/KrogerCart.tsx` |
| The evaluation counts purchase attempts with no purchase. | `backend/app/evaluation_purchase.py` |
