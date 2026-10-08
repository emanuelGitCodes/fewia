# Pantry verification probes

These scripts preserve the focused checks used during the pantry follow-up
investigation. They call the existing evaluation runner with real Bedrock.
They do not run a full benchmark or certify a general release.

| Script | Scope |
|---|---|
| `pantry_live_probe.py` | Three repeats per selected canonical case, with tools enabled. |
| `pantry_phrase_probe.py` | One observation for each of four pantry wording variants. |

## Requirements

- Python 3.12 and the backend dependencies managed by `uv`.
- A clean Git checkout at the revision supplied with `--revision`.
- A valid `fewia-bedrock-dev` AWS profile with access to the configured model.
- A new output directory outside the checkout, or in an ignored path.

Run the scripts from `backend/` with `PYTHONPATH=.`. They use
`us.amazon.nova-2-lite-v1:0` in `us-east-1`. The manifest records 4096 maximum
tokens, temperature zero, and low reasoning effort. The scripts use the
existing Bedrock provider; they do not read or print credentials themselves.
If the profile lives in a separate credentials file, set
`AWS_SHARED_CREDENTIALS_FILE` to that file's path before running a probe.

Do not use `python -O`; the preserved scripts use assertions for their
revision, clean-tree, and selection checks. The scripts make paid provider
calls. `--help` displays usage without making a model call.

## Canonical checks

From the repository root:

```bash
cd backend
PYTHONPATH=. uv run python ../eval/probes/pantry_live_probe.py \
  --revision "$(git rev-parse HEAD)" \
  --cases F05,F01,F02,F04,A02,A04,X03,X02 \
  --output /private/tmp/fewia-pantry-canonical-new
```

The default selection is `F05,F01,F02,F04,A02,A04,X03`, for 21 observations.
The example adds `X02`, for 24 observations. Use unique, supported case IDs.
The script preserves the canonical messages and expected outcomes.

## Wording checks

From `backend/`:

```bash
PYTHONPATH=. uv run python ../eval/probes/pantry_phrase_probe.py \
  --revision "$(git rev-parse HEAD)" \
  --output /private/tmp/fewia-pantry-phrases-new
```

The four variants cover preserving pantry stock during a servings change,
stock held at home, a contraction in a stock statement, and a repurchase.
Each variant changes the final user message in a copy of its source case.
The expected outcome stays unchanged. The report labels these observations
as ad-hoc wording checks, separate from canonical benchmark slots.

## Results and interpretation

Each script writes `slots.jsonl` incrementally and `report.json` on completion.
The report records the source revision, corpus hash, run times, and results.
Each phrase variant has its own manifest. Existing output directories cause
the scripts to stop; use a new path for each run.

A zero process exit does not mean every observation passed. Inspect quality
statuses in the report. Execution status and scored quality have different
meanings. A failed or interrupted run can leave only a partial journal.
Preserve failed observations when comparing revisions.

These files preserve the original scripts' syntax trees. Formatting and file
names changed. The scripts' behavior, model settings, report keys, case
selection, and expected outcomes did not change. The scripts evaluate the
current checkout; results from another revision do not prove its behavior.

Original temporary file SHA-256 values:

| Original file | SHA-256 |
|---|---|
| `fewia-pantry-live-probe.py` | `a18083bb2942c2823ae291c2dadffd0ea1a5c0463e0068dbc1a1dd08f93f5469` |
| `fewia-pantry-phrase-probe.py` | `39ffe08b9599a035c80689cb33bbfb7e6cfa4f97f9ddbbd6e0b5cbcd533042a7` |
