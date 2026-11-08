# Verification record

| Check | Revision | Observed result |
|---|---|---|
| Adapter and Compose launcher | `2e03d32c` | Ruff, formatting, strict mypy, PostgreSQL-backed tests, and Compose passed. Pytest reported 18,335 passed and one skipped. |
| Runner and comparator on the measured revision | `2295a0ed` | Ruff, formatting, strict mypy, and PostgreSQL-backed tests passed. Pytest reported 18,420 passed and one skipped. |
| Journal-integrity follow-up | `229be439` | The same gates passed. Pytest reported 18,426 passed and one skipped. |
| Live US Luna conversation check | Adapter worktree | Luna returned a tool call and accepted the tool result. Both turns of C07 passed the shared scorer. |
| Live local API and worker smoke | Adapter worktree | Compose started. The chat job proposed two servings of bean tacos. Apply persisted a new plan revision. |
| Clean source ZIP | `2295a0ed` | A locked dependency install passed. The conversation fixture recorded all 123 turns without provider credentials. |
| Matched fixture comparison | `2295a0ed` | Both fixture arms passed all 75 repeats. The comparator rejected a changed tool-definition hash. |
| Planning control and live trial completeness | `3f0fcf1f` | The offline mock verified identical inputs and schema. An independent calculation agreed with the planner for all 12 cases. All 72 live trials were recorded and formatted correctly. |

The independent review approved the adapter and the journal-integrity follow-up. The earlier review found two issues. Compose accepted relative host paths, and the comparator accepted a changed journal with the same turn keys. The launcher and checksum checks address those issues.

A throwaway redirect mutation caused both endpoint tests to fail. Removing the matching guard caused six manifest tests to fail. Removing journal-hash validation caused four tampering and missing-hash tests to fail. The repaired comparator reproduced the matched live report from the attested copies.

Earlier local gates found five legacy tests that assumed all model profiles used AWS regions. The tests were updated to preserve the Nova cases and check Luna's supported regions. Final gate output is attached. The live browser was not driven by an automated browser test. The isolated smoke check used the same browser API endpoints.
