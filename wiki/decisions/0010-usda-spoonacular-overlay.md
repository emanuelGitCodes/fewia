# 0010 — Park Instacart. Use USDA nutrition and Spoonacular cost

- Date: 2026-09-11
- Status: accepted

## Decision

Park the Instacart development handoff. Keep the Instacart adapter in the
repository. Do not delete it. Keep `instacart_configured` false until IDP
access exists.

Store nutrition facts from USDA FoodData Central. Those facts MAY live in
the catalog. Cite USDA. They are not a medical claim.

Show Spoonacular average supermarket cost as a labeled overlay. Budget
acceptance MUST still use FEWIA sample-catalog cents. Spoonacular cost MUST
NOT change servings or drop ingredients.

Pull request [58](https://github.com/emanuelGitCodes/fewia/pull/58) merged
the domain contracts.

## Why Instacart stopped

Instacart Developer Platform (IDP) is not accepting new applications. There
is no waitlist. Source:
[https://company.instacart.com/business/developers](https://company.instacart.com/business/developers).

The operator MUST NOT scrape Instacart. The operator MUST NOT use another
person's key. The operator MUST NOT invent a shopping URL that looks like
Instacart.

## What Instacart was going to provide

IDP `POST /idp/v1/products/products_link` returns a link to an Instacart
page. The shopper finishes matching and checkout there.

Instacart's own FAQ says public IDP partners do not receive Instacart
catalog data. IDP was never going to give FEWIA live shelf prices,
nutrition facts, or pickup locations.

The accepted brief already said Instacart links prove handoff, not prices.
Sample catalog prices stay labeled as estimates.

## Options that were rejected

**Walmart developer APIs.** `developer.walmart.com` is a seller Marketplace
API. A seller manages that seller's items, inventory, and orders. It is not
a public grocery search for a student meal planner.

**Publix.** No public catalog or price API was found for third-party apps.

**Cheapest-store shopping.** Retailers do not publish APIs that let an app
compare live shelf prices across Walmart, Publix, and Instacart. Scraping
those sites is not an accepted path.

**Spoonacular as the only price source.** Spoonacular forbids storing prices,
nutrition, and ingredients except a one-hour cache. Evaluation gold needs
stable cents. A live Spoonacular total would change between runs.

**USDA as a price source.** FoodData Central is nutrition, not store prices.

## What Spoonacular does provide

Spoonacular returns ingredient types, recipe nutrition, grocery product
titles and UPCs, and `estimatedCost` in US cents. `pricePerServing` is the
same kind of average. Their FAQ says cost is aggregated supermarket data.
Prices vary by store. Location-based pricing is not available.

Spoonacular does not create an Instacart, Walmart, or Publix cart. Its
shopping list lives on Spoonacular.

Spoonacular terms: you MAY store recipe id, title, and image URL forever.
You MAY cache other fields for one hour. After one hour you MUST delete
that cache. If you stop using the API, you MUST delete all obtained data.
You MUST NOT store hashed or transformed prices to keep them longer. You
MUST credit recipe sources. You MUST show disclaimers for allergies,
estimated cost, and nutrition.

Free plan: 50 points per day. Academic access exists through RapidAPI.

## What USDA does provide

USDA FoodData Central is public domain (CC0). Anyone MAY use the API with
a data.gov key. You MAY store the facts. Rate limit is 1,000 requests per
hour per IP by default. Cite FoodData Central.

USDA does not give package prices or pickup locations.

Open Food Facts remains an unused alternative for barcode nutrition.

## Hybrid rules that hold today

| Job | Source |
| --- | --- |
| Budget and plan acceptance | FEWIA sample catalog, integer cents |
| Nutrition | USDA FoodData Central, stored |
| Extra recipe or ingredient cost | Spoonacular, live or one-hour cache, labeled |
| Retailer cart | Instacart adapter, parked |

The planner MUST keep using FEWIA cents for `accepted` and `total_cents`.
Spoonacular cost is a second line. USDA nutrition is a second line.

Notices:

- Catalog: `SAMPLE_ESTIMATE_NOTICE` in `backend/app/domain/grocery.py`
- USDA: `USDA_NUTRITION_NOTICE` in `backend/app/domain/nutrition.py`
- Spoonacular: `SPOONACULAR_COST_NOTICE` in
  `backend/app/domain/supermarket_estimate.py`

## Questions and answers

**Can we get around a closed IDP?** No.

**Did Instacart give nutrition and live prices?** No. Public IDP gives a
handoff link.

**Can we connect Walmart and Publix and pick the cheapest?** Not through
public APIs. Do not scrape.

**Is average Spoonacular cost better than nothing?** Yes, as a labeled
overlay. It is not a store price.

**Can we cache Spoonacular prices for a day?** No. The cache window is one
hour, not one day.

**What Spoonacular fields MAY stay forever?** Recipe id, recipe title, and
recipe image URL.

**Where do API keys go?** Not in source. Not in `wiki/`. Not in chat. Not in
`.env.example`. Use local files with mode `600`. Point `.env` at those
files. Git ignores `.env`.

**When do adapters read the keys?** After the Spoonacular HTTP adapter
ships. Contracts in pull request 58 do not read keys.

**Did the operator test Spoonacular?** Yes. The operator reported a live
response. This page does not record the key or the payload.

## Build order

Independent of the merged handoff stack (pull requests 48–50) and the
evaluation stack (pull requests 51–57).

1. Domain contracts. Done. Pull request 58.
2. Frozen USDA nutrition map for catalog ingredients. No live key required
   if FDC ids and facts are stored from public data.
3. Spoonacular HTTP adapter with a one-hour cache. Needs
   `FEWIA_SPOONACULAR_KEY_FILE`.
4. Attach the extra estimate without changing planner totals.
5. Frontend labels for USDA nutrition and Spoonacular cost.

Instacart routes stay. The shopping button stays hidden while
`instacart_configured` is false.

## Secrets

`.env.example` on `main` lists empty `FEWIA_USDA_FDC_KEY` and
`FEWIA_SPOONACULAR_KEY` plus `*_KEY_FILE` path placeholders. Adapters MUST
prefer the file path. Inline key variables MUST stay empty in
`.env.example`.

If a real key was written into a tracked file, rotate that key. This wiki
MUST NOT copy a key.

## Consequences

[0008](0008-grocery-bot-pivot.md) still requires real Bedrock evidence.
Live Instacart development evidence is blocked until IDP reopens. Plaid
Sandbox remains a separate vendor. Nutrition moves off the wishlist for
the hybrid stack. Live retailer prices remain unverified.

This MUST NOT claim live Instacart, Walmart, or Publix prices.
This MUST NOT claim medical nutrition advice.

## Addendum — 2026-09-12

The original one-hour cache assumption is incomplete.

Current Spoonacular terms live in the Prohibitions section at
https://spoonacular.com/food-api/terms.
That section says caching of user-requested data needs prior written
permission. The same section sets a one-hour maximum when permission
exists. The same section says prices and derived or transformed data
are not storable. This repository has no written-permission record.

The HTTP adapter uses no cache. Each `estimate_ingredient_cents` call
MUST issue a fresh HTTP GET. The provider MUST NOT keep responses or
costs on the instance. The provider MUST NOT export `CACHE_SECONDS`.
The constructor MUST NOT take a clock. A later written permission MAY
allow a cache. That path needs a separate approval. This page MUST NOT
treat that path as active.

The deterministic sample catalog stays unchanged. Stored USDA facts
stay unchanged.

Job results do not keep a root `supermarket_estimate`.
The request-local estimate API and the explicit UI overlay now exist.
Operators follow
[docs/SUPERMARKET_ESTIMATES.md](../../docs/SUPERMARKET_ESTIMATES.md).
This page MUST NOT treat a one-hour store as active.

## Addendum — 2026-09-12 overlay retention

The worker does not estimate Spoonacular cost.
`finish_job` and both GET job routes strip root `supermarket_estimate`.
Migration `0008` removes that root field from `jobs.result` only.
It deletes no rows and no evidence.

`GET /grocery/jobs/{job_id}/supermarket-estimate` is request-local.
The UI uses an explicit `Check supermarket estimate` button.
The overlay is current-view state.
It MUST NOT change `accepted` or `total_cents`.
Budget cents stay on the sample catalog.
USDA macros stay stored.

Optional runtime binding uses `--spoonacular-key-file`.
Omit the flag to keep the AWS-only path.
See [docs/SUPERMARKET_ESTIMATES.md](../../docs/SUPERMARKET_ESTIMATES.md).
