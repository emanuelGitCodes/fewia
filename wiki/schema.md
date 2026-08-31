# Wiki schema

This wiki records the work done and the decisions made in FEWIA. It
follows the llm-wiki pattern: the sources stay immutable, the agent
maintains the wiki, and this file defines the conventions.

## Layers

- `docs/` holds the sources: the proposal, the MVP plan, the course
  material. Agents MUST NOT edit a source.
- `wiki/` holds the knowledge base. Agents own it and keep it current.
- This file is the schema. `CLAUDE.md` points here.

## Layout

```text
wiki/
├── schema.md        # this file
├── index.md         # catalog of every page, by category
├── log.md           # append-only chronological record
├── decisions/       # one page per decision, numbered
└── phases/          # one page per completed phase
```

## Conventions

- One page holds one topic. Link related pages with relative Markdown
  links.
- A decision page is named `NNNN-short-slug.md` and states: the
  decision, the date, the options considered, the reason, and the
  consequences.
- A phase page states: what shipped, the verification result, the
  commits or pull requests, and open items.
- `log.md` is append-only. Each entry carries a date and one short
  paragraph. Agents MUST NOT edit or delete an existing entry.
- Every new page gets one line in `index.md`.
- History, dates, status, and justification belong here, not in code
  comments. The `house-style` skill states this rule.

## Operations

- **Record**: after a work item merges or a decision lands, the agent
  that did the work adds a log entry and updates or creates the pages
  it touched.
- **Query**: read `index.md` first, then follow links. Use `/graphify
  query` for structural questions about the corpus.
- **Lint**: at each phase checkpoint, check for contradictions, stale
  claims, orphan pages, and missing links. Fix what you find.
