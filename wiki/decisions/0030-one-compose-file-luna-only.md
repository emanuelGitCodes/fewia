# 0030 — One compose file, and the stack runs Luna only

- Date: 2026-11-08
- Status: accepted
- Amends: [0027 — GPT-6 Luna is the default local chat provider](0027-luna-default-chat-provider.md) and [0029 — `make up` starts Kroger in fixture mode](0029-kroger-fixture-mode-default.md)

## Decision

`compose.yaml` starts the whole stack. It gives the worker the OpenAI key as
a Compose secret and runs Kroger in fixture mode. GPT-6 Luna is the only chat
model in the stack. `make up` is the start command.

`compose.kroger.yaml` is the only overlay. It switches Kroger to live mode
and mounts the credential files. `make up-kroger-live` starts it.

`compose.openai.yaml`, `compose.bedrock.yaml`, `compose.kroger-fixture.yaml`,
`make up-bedrock`, and `make up-offline` no longer exist. Without a working
OpenAI key, `make up` fails before it builds.

Amazon Bedrock stays in the evaluation command-line tools, which run outside
Docker and compare Nova with Luna. `BedrockConverseProvider` stays in the
code for those tools.

The launcher prints one line per stage and shows the Docker Compose output.
It checks the OpenAI key against the OpenAI models endpoint before it builds.
HTTP 401 or 403 stops the launch with a message that names the fix.

## Options considered

1. Keep the overlays and the three start targets. A grader must then choose
   among several commands and files.
2. Keep a no-key offline mode. The chat, the core of the project, is then
   off without a clear reason.
3. One file, one command, a key check first. Chosen.

## Reason

The owner chose this on 2026-11-08. A fresh start on the owner's machine
failed: the chat answered "FEWIA did not answer" because OpenAI rejected the
key with HTTP 401, and the launcher showed no output during the build. The
course grader runs the code ZIP, and the rubric gives 30% to code
runnability. The owner judges Luna the better model for the product. The
matched 2026-11-07 study measured an all-check pass difference of +1.33
percentage points for Luna over Nova, with a 95% interval of −14.7 to +18.7.
That descriptive interval includes zero, so the single run leaves a general
quality advantage uncertain.

## Consequences

- A grader needs only an OpenAI key and `make up`.
- A Bedrock comparison runs through the evaluation tools, not the browser.
- The key check sends the key to OpenAI once per launch. The launcher never
  prints it.
