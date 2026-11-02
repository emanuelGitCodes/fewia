# Conversation quality experiment

This directory defines a partial experiment for `conversation-eval-v1.4`. It does not replace the full 96-slot suite.

`selection.json` selects scenarios and repeats from the full corpus. It covers 22 logical user turns per arm. From `backend/`, pass these options to `python -m app.evaluate_conversation`:

```text
--selection-file ../eval/experiments/conversation-quality/selection.json
--max-chat-turns 22
```

Each arm MUST use at most 22 turns. The two arms use 44 paired turns total. The coordinator MUST reserve four turns total. The combined budget is 48 turns.

Each arm MUST write to a new output directory. Experiment runners MUST keep completed artifacts immutable. Experiment runners MUST use a new directory for each rerun. Experiment records MUST contain hashes and aggregate fields only. Experiment records MUST NOT contain reply text or unmatched tokens.

A valid comparison MUST use the same code except for prompt text. Keep the model profile, region, and other run inputs fixed.
