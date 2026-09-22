# Grocery completion review stack

New feature work stopped at 8% weekly remaining on 2026-09-22 09:15:18 UTC.
This index covers 65 feature, test, and documentation branches plus one final handoff document branch.
Each branch MUST stay at or under 150 added application lines.
The largest recorded application addition in this stack is 149 lines.

Tests, documentation, lockfiles, and generated evidence do not count toward the 150-line cap.

## Review publication

Each row links its review branch. Pull requests are listed on GitHub. Review changes in the order below.
Branch links remain publication targets until pushed.

GitHub pull request list: [https://github.com/emanuelGitCodes/fewia/pulls](https://github.com/emanuelGitCodes/fewia/pulls)

## Merge order and parent retarget

Reviewers MUST read the stack bottom-up.
`codex/app-completion-01` uses parent `main`.
Each later branch uses the previous `codex/app-completion-NN` branch as parent.

Agents MUST NOT merge.
Agents MUST NOT push to `main`.
A human merge of a parent MUST leave that parent in place until each child retargets.

## Related records

- Current backlog: [APP_COMPLETION_BACKLOG.md](APP_COMPLETION_BACKLOG.md)
- Evaluation guide: [../docs/GROCERY_EVALUATION.md](../docs/GROCERY_EVALUATION.md)
- Current checkpoint: [../wiki/phases/grocery-completion-20260922.md](../wiki/phases/grocery-completion-20260922.md)
- Evidence classes: [../docs/evidence/README.md](../docs/evidence/README.md)

The evidence README is a separate writer deliverable.

## Branch table

| Order | Description | Added application lines | Parent | Review branch |
| ---: | --- | ---: | --- | --- |
| 1 | Preserve nutrition and legacy plans in frontend contracts | 119 | main | [codex/app-completion-01](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-01) |
| 2 | Show nutrition per serving meal and selected plan | 143 | codex/app-completion-01 | [codex/app-completion-02](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-02) |
| 3 | Remove Spoonacular response caching and sanitize parse failures | 4 | codex/app-completion-02 | [codex/app-completion-03](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-03) |
| 4 | Handle the live US cents label without currency conversion | 16 | codex/app-completion-03 | [codex/app-completion-04](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-04) |
| 5 | Remove supermarket estimates from durable job results | 45 | codex/app-completion-04 | [codex/app-completion-05](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-05) |
| 6 | Validate saved plan quantities for fresh price requests | 98 | codex/app-completion-05 | [codex/app-completion-06](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-06) |
| 7 | Serve request-only supermarket estimates with no-store responses | 96 | codex/app-completion-06 | [codex/app-completion-07](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-07) |
| 8 | Add an uncached supermarket estimate client | 41 | codex/app-completion-07 | [codex/app-completion-08](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-08) |
| 9 | Bound supermarket estimate state to the active view | 122 | codex/app-completion-08 | [codex/app-completion-09](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-09) |
| 10 | Restore the request-only supermarket estimate control | 40 | codex/app-completion-09 | [codex/app-completion-10](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-10) |
| 11 | Expose catalog identifiers to grocery chat tools | 27 | codex/app-completion-10 | [codex/app-completion-11](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-11) |
| 12 | List owned Plaid Items for explicit spending refresh | 45 | codex/app-completion-11 | [codex/app-completion-12](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-12) |
| 13 | Add typed Plaid refresh browser requests | 138 | codex/app-completion-12 | [codex/app-completion-13](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-13) |
| 14 | Observe bounded chat failure with a fake model provider | 147 | codex/app-completion-13 | [codex/app-completion-14](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-14) |
| 15 | Assess the provider outage evaluation scenario | 9 | codex/app-completion-14 | [codex/app-completion-15](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-15) |
| 16 | Observe model evaluation conversations without scoring claims | 149 | codex/app-completion-15 | [codex/app-completion-16](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-16) |
| 17 | Bound Plaid refresh polling and cancellation | 116 | codex/app-completion-16 | [codex/app-completion-17](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-17) |
| 18 | Track explicit Plaid refresh and safe retries | 148 | codex/app-completion-17 | [codex/app-completion-18](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-18) |
| 19 | Show explicit Sandbox connection refresh controls | 143 | codex/app-completion-18 | [codex/app-completion-19](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-19) |
| 20 | Refresh spending and invalidate prior estimates | 61 | codex/app-completion-19 | [codex/app-completion-20](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-20) |
| 21 | Test grocery browser journeys in CI | 60 | codex/app-completion-20 | [codex/app-completion-21](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-21) |
| 22 | Run repeated fixture and model observation batches | 144 | codex/app-completion-21 | [codex/app-completion-22](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-22) |
| 23 | Emit each completed evaluation slot | 25 | codex/app-completion-22 | [codex/app-completion-23](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-23) |
| 24 | Return safe catalog conflicts to the planning agent | 108 | codex/app-completion-23 | [codex/app-completion-24](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-24) |
| 25 | Report measured evaluation latency and token coverage | 148 | codex/app-completion-24 | [codex/app-completion-25](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-25) |
| 26 | Persist evaluation journals and atomic results | 147 | codex/app-completion-25 | [codex/app-completion-26](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-26) |
| 27 | Ground public chat answers in validated plan facts | 125 | codex/app-completion-26 | [codex/app-completion-27](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-27) |
| 28 | Keep unresolved chat estimates marked as previous | 13 | codex/app-completion-27 | [codex/app-completion-28](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-28) |
| 29 | Run evaluation batches with recoverable evidence | 145 | codex/app-completion-28 | [codex/app-completion-29](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-29) |
| 30 | Add controlled protocol evaluation fixture | 62 | codex/app-completion-29 | [codex/app-completion-30](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-30) |
| 31 | Add isolated refresh evaluation fixture | 145 | codex/app-completion-30 | [codex/app-completion-31](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-31) |
| 32 | Observe refresh failure without advancing freshness | 101 | codex/app-completion-31 | [codex/app-completion-32](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-32) |
| 33 | Observe bounded malformed and unknown tool behavior | 108 | codex/app-completion-32 | [codex/app-completion-33](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-33) |
| 34 | Validate explicit dated model token rates | 106 | codex/app-completion-33 | [codex/app-completion-34](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-34) |
| 35 | Estimate known token costs without inventing missing usage | 78 | codex/app-completion-34 | [codex/app-completion-35](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-35) |
| 36 | Validate structural evaluation values and completed turns | 89 | codex/app-completion-35 | [codex/app-completion-36](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-36) |
| 37 | Score controlled protocol failures against observed bounds | 89 | codex/app-completion-36 | [codex/app-completion-37](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-37) |
| 38 | Include controlled refresh and protocol reports in evaluation batches | 17 | codex/app-completion-37 | [codex/app-completion-38](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-38) |
| 39 | Make the request-only supermarket overlay reproducible | 12 | codex/app-completion-38 | [codex/app-completion-39](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-39) |
| 40 | Score final observed grocery plans without overstating quality | 142 | codex/app-completion-39 | [codex/app-completion-40](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-40) |
| 41 | Add isolated uncertain-handoff evaluation fixture | 87 | codex/app-completion-40 | [codex/app-completion-41](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-41) |
| 42 | Observe uncertain handoffs without automatic replay | 99 | codex/app-completion-41 | [codex/app-completion-42](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-42) |
| 43 | Persist final-plan assessments and evaluation source region | 8 | codex/app-completion-42 | [codex/app-completion-43](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-43) |
| 44 | Align grocery verification scope and model requirements | 0 | codex/app-completion-43 | [codex/app-completion-44](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-44) |
| 45 | Include uncertain-handoff checks in fixture evaluations | 3 | codex/app-completion-44 | [codex/app-completion-45](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-45) |
| 46 | Summarize evaluation evidence without merging unlike scores | 127 | codex/app-completion-45 | [codex/app-completion-46](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-46) |
| 47 | Validate evaluation report values | 85 | codex/app-completion-46 | [codex/app-completion-47](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-47) |
| 48 | Add a structured planning reference | 72 | codex/app-completion-47 | [codex/app-completion-48](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-48) |
| 49 | Render scoped evaluation results as Markdown | 116 | codex/app-completion-48 | [codex/app-completion-49](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-49) |
| 50 | Record current grocery completion evidence | 0 | codex/app-completion-49 | [codex/app-completion-50](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-50) |
| 51 | Write evaluation Markdown without overwriting files | 53 | codex/app-completion-50 | [codex/app-completion-51](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-51) |
| 52 | Render dated token-cost estimates | 118 | codex/app-completion-51 | [codex/app-completion-52](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-52) |
| 53 | Isolate local P05 integration test resources | 0 | codex/app-completion-52 | [codex/app-completion-53](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-53) |
| 54 | Export saved evaluation batches as Markdown | 138 | codex/app-completion-53 | [codex/app-completion-54](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-54) |
| 55 | Prioritize the latest pantry instruction in chat context | 13 | codex/app-completion-54 | [codex/app-completion-55](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-55) |
| 56 | Verify duplicate delivery through local handoff and S3 | 0 | codex/app-completion-55 | [codex/app-completion-56](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-56) |
| 57 | Accept dated pricing in evaluation reports | 39 | codex/app-completion-56 | [codex/app-completion-57](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-57) |
| 58 | Pass the explicit server cap into chat context | 30 | codex/app-completion-57 | [codex/app-completion-58](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-58) |
| 59 | Document reproducible grocery evaluation commands | 0 | codex/app-completion-58 | [codex/app-completion-59](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-59) |
| 60 | Compare final plans with a structured reference | 138 | codex/app-completion-59 | [codex/app-completion-60](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-60) |
| 61 | Keep only tool calls in assistant tool-cycle history | 16 | codex/app-completion-60 | [codex/app-completion-61](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-61) |
| 62 | Include reference comparisons in evaluation reports | 41 | codex/app-completion-61 | [codex/app-completion-62](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-62) |
| 63 | Render bounded typed refusal replies | 64 | codex/app-completion-62 | [codex/app-completion-63](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-63) |
| 64 | Observe secret and purchase refusal scenarios | 3 | codex/app-completion-63 | [codex/app-completion-64](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-64) |
| 65 | Refresh API addresses in the Docker web proxy | 8 | codex/app-completion-64 | [codex/app-completion-65](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-65) |
| 66 | Finalize grocery completion handoff | 0 | codex/app-completion-65 | [codex/app-completion-66](https://github.com/emanuelGitCodes/fewia/tree/codex/app-completion-66) |
