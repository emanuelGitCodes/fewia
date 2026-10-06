---
name: wiki-log
description: Record a finished work item, a merged stack, or a decision in the wiki. Appends one dated entry to wiki/log.md and creates a numbered decision page when a choice was made. Use when the user says "record this", "log this", "write the decision", or after a work item merges.
argument-hint: "<what happened> | decision <title>"
---

# Wiki log

The wiki holds history, status, and justification. Code comments hold
none of those. This skill writes the two page types the schema in
`wiki/schema.md` defines.

## Log entry

1. Read the last three entries of `wiki/log.md` for the current voice.
2. Append one entry at the end. Use `references/log-entry.md` as the
   shape. Never edit or delete an earlier entry. A hook denies that.
3. One short paragraph. Name the pull request numbers, the merge SHAs,
   and the verification result. Sentences stay under 25 words.
4. State open questions as facts: who decides, and between what.

## Decision page

1. Take the next number from `wiki/decisions/`. Four digits.
2. Copy `references/decision-template.md` to
   `wiki/decisions/NNNN-short-slug.md` and fill every section.
3. Add one line under `## Decisions` in `wiki/index.md`, in order.
4. When the decision amends an earlier one, say so in both pages'
   status lines with a relative link.
5. Append a log entry that names the decision.

## Before you finish

- Run the house-style rules on the new text: active voice, one idea per
  sentence, MUST and MAY only in uppercase when they state a rule.
- A log entry MUST NOT contain model-generated evaluation prose. Decision
  0014 and the course contract forbid it. Report numbers and file paths.
- Commit the wiki change on the work branch. The pull request body links
  the entry.
