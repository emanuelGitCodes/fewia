# Spoonacular supermarket estimate

This runbook covers the optional labeled overlay on the local grocery demo.
The overlay does not replace the sample catalog budget.
The overlay is not a live store price.

Every sample estimate MUST show this notice:

> Estimated from the demo price catalog. Instacart prices, availability,
> taxes, delivery fees, and tips are not verified.

## Local stack

The demo uses React and TypeScript chat, FastAPI, PostgreSQL, a worker,
and Floci.
Floci supplies local SQS jobs and S3 evaluation export paths.
Real Bedrock is the approved chat path through `LLMProvider`.
Plaid Sandbox adapters exist. Live Sandbox proof remains pending.
Instacart development shopping-list links stay parked.
`instacart_configured` stays false while IDP is closed.

The catalog supports ten meals: chicken tacos, bean tacos, vegetable
pasta, chicken-and-rice bowls, lentil soup, chickpea curry, vegetable
stir-fry, baked potatoes with beans, breakfast burritos, and overnight
oats.
A request uses one to three (1-3) meals.
Each meal uses one to eight (1-8) servings.

## What stays authoritative

Budget acceptance uses FEWIA sample-catalog integer cents.
The planner sets `accepted` and `total_cents` from that catalog.
Spoonacular cost MUST NOT change `accepted` or `total_cents`.
Spoonacular cost MUST NOT change servings or drop ingredients.

Stored USDA facts supply calories, protein, carbs, and fat.
Those four fields are the macro set.
The overlay MUST NOT add micronutrients.
Consumed recipe quantities include pantry items.
Macros are per serving and per plan.
USDA facts stay stored in the catalog.
They need no runtime FoodData Central key.

The worker MUST NOT run a Spoonacular estimator.
Job results MUST NOT keep a root `supermarket_estimate`.
Migration `0008` removes that root field from `jobs.result` only.
It deletes no rows and no evidence.

## Optional provider

The overlay is optional.
Omit `--spoonacular-key-file` to keep the AWS-only runtime path.
An unconfigured lookup returns HTTP 503.
Success and error responses MUST set `Cache-Control: no-store`.

Each lookup is a fresh HTTP GET.
The provider MUST NOT cache responses or costs.
The provider is request-local.
The process closes it after the call.

`GET /grocery/jobs/{job_id}/supermarket-estimate` is the overlay route.
The caller MUST own the job.
The job MUST be a succeeded manual or chat plan.
The route validates plan quantities.
It discards partial prices.
API admission deadline is 20 seconds plus existing per-call timeouts.
The browser waits 45 seconds.
Operators MUST NOT claim a hard 40-second wall-clock guarantee.

Official Get Ingredient Information documents US Cents:
https://spoonacular.com/food-api/docs#Get-Ingredient-Information
The adapter pins `locale=en_US`.
It treats those documented aliases as minor units.
It MUST NOT apply a 100x conversion.
Unknown, malformed, negative, or nonfinite currency stays unavailable.
That rule is live contract compatibility.
It is not retail-price validation.

Price data MUST NOT enter logs, snapshots, or model inputs.
Fixture test values are fictional.
Those values MAY appear in tests.

## Current-view UI

The UI shows an explicit `Check supermarket estimate` button.
The UI MUST NOT fetch the overlay automatically.
The overlay is current-view state only.
The UI clears it on a new request.
The UI clears it on a plan change, a dirty plan, or a pending plan.
The UI clears it on unmount, a hidden tab, and 5-minute expiry.
A plan edit clears a prior overlay.
Legacy job prices are discarded.
Budget cents and USDA macros stay.

## Host key file

Store the key outside Git and outside the checkout.

- Generic example path: `$HOME/.config/fewia/spoonacular/api-key`
- File mode: `600`
- Parent directory mode: `700`

The path MUST be absolute.
The file MUST NOT be a symlink.
Ancestors MUST NOT be symlinks.
The file MUST be a regular file owned by the current user.
The file MUST be owner-readable and private.
Size MUST be 1 through 8192 bytes.
The parent MUST deny group and other access.
The path MUST stay outside the chosen checkout.
The path MUST stay outside the source checkout.

The launcher validates that metadata.
The launcher MUST NOT read key contents.
Key values MUST NOT appear in the environment or argv.
Do not write a secret into this runbook.
Do not paste a command that prints or copies a key.

## Bind the overlay

Start from the source checkout or a Git worktree of that source.
Run:

```bash
uv run --project backend python -m infra.bedrock_runtime --project fewia-macros --spoonacular-key-file "$HOME/.config/fewia/spoonacular/api-key"
```

Default omit of `--spoonacular-key-file` keeps AWS-only Compose.

`compose.spoonacular.yaml` applies only to `api`.
It sets `FEWIA_SPOONACULAR_KEY_FILE=/run/fewia/spoonacular-key`.
It binds the host file read-only to `/run/fewia/spoonacular-key`.
The bind sets `create_host_path: false`.
The worker MUST NOT receive a Spoonacular key mount.
Existing AWS API and worker mounts stay.
The runtime profile `fewia-bedrock-runtime` stays.

A normal Docker restart keeps a bound mount.
Recreation MUST pass `--spoonacular-key-file` again.
Operators MUST reload nginx after API recreation.

## Evidence classes

| Class | What it may prove |
| --- | --- |
| Deterministic | Sample catalog cents, stored USDA macros, stripped job results |
| Fixture | Demo spending and fictional overlay test values |
| Emulator | Floci SQS jobs and Floci S3 export paths |
| Sandbox | Plaid Sandbox adapters. Live Sandbox proof is pending |
| Live | Real Bedrock chat. Optional Spoonacular overlay when configured |
| Deployed | IAM runtime user and stacks in `infra/bedrock/UNATTENDED.md` |

Fixture data is not a verified retailer or bank claim.
A numeric overlay is not a verified store, tax, fee, or tip.
Stored USDA facts are not medical advice.
This runbook MUST NOT record an actual Spoonacular price.

## Related records

- [Decision 0010](../wiki/decisions/0010-usda-spoonacular-overlay.md)
- [Grocery MVP checkpoint](../wiki/phases/grocery-mvp-checkpoint.md)
- [Unattended Bedrock runtime](../infra/bedrock/UNATTENDED.md)
