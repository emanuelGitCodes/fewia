# FEWIA browser workflow benchmark

Revision f0f7b7d80159f4ec182138bd83479df8e27a95b7. One measured browser journey per case. Both used live GPT-6 Luna through the OpenAI US endpoint. The local stack ran the application at this revision. Kroger account status, store lookup, and products were fixtures. The real FEWIA API built each preview from a PostgreSQL plan revision.

Both cases began with two servings of Bean tacos, an $8.06 basket, and a $40.00 cap. The request asked to remove only olive oil, cumin, and salt from the pantry. After Luna proposed the same three removals in both cases, the browser set the cap to $17.03 or $17.02 and clicked Apply.

| Stage | Apply at $17.03 | Reject at $17.02 |
| --- | ---: | ---: |
| Submit to HTTP 202 | 96.97 ms | 88.98 ms |
| Submit to proposal visible | 3,186.33 ms | 3,161.83 ms |
| Provider calls, total | 2,730.49 ms across 2 calls | 2,367.94 ms across 2 calls |
| Proposal lookup on API | 2.35 ms | 2.96 ms |
| Apply to visible result | HTTP 200, 51.83 ms | HTTP 409, 56.69 ms |
| Store search to selection, Kroger fixture | 82.69 ms | 82.98 ms |
| Cart preview click to visible results, Kroger fixture | 56.47 ms | 56.19 ms |
| Cart preview on API, Kroger fixture | HTTP 200, 3.75 ms | HTTP 200, 3.14 ms |
| Submit to cart visible, including browser checks | 3.752 s | 3.645 s |
| Estimated model cost | $0.00025322 | $0.00025025 |

The valid Apply returned HTTP 200. The UI showed $17.03 and PostgreSQL added one applied revision with the expected meals and pantry. The fixture cart preview showed seven matched ingredients and zero unmatched.

The one-cent case returned HTTP 409 with a 1,703-cent total and a 1,702-cent limit. The UI stayed at $8.06. Apply left all saved revisions and proposal rows unchanged and kept the proposal pending. The fixture cart preview showed four matched ingredients and zero unmatched, excluding the pantry items.

Apply validated the current cap. Its successful saved revision still contained the original $40.00 proposal cap. The cart preview flow saved a separate snapshot with the active cap, $17.03 or $17.02, and preserved the expected meals and pantry. The fixture transport received only token, store, and product requests. The two browser journeys made zero cart-add or checkout requests.

The completed pair used an estimated $0.00050347 in model tokens. The initial live pair used $0.00093423. Its cart responses were HTTP 200, and the first harness stopped before verifying cart rendering because it compared the active cap against the original snapshot. Total estimated cost with reported usage was $0.00143770. Two earlier attempts with a rejected key returned HTTP 401 and reported no token usage.

Pricing uses $0.11 per million uncached input tokens, $0.011 per million cached input tokens, and $0.55 per million output tokens, including the 10% US regional uplift. The completed pair reused cached input. Browser timing includes polling, UI actions, and the harness checks between stages. The Kroger fixture latency measures the local path. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

[Machine-readable results](results.json)
