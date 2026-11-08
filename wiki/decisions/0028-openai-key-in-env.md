# 0028 — The OpenAI key goes in `.env`

- Date: 2026-11-07
- Status: accepted
- Amends: [0027 — GPT-6 Luna is the default local chat provider](0027-luna-default-chat-provider.md)

## Decision

The operator puts the OpenAI API key in `.env` as `FEWIA_OPENAI_API_KEY`.
`compose.openai.yaml` turns that value into a Compose secret. Only the
`worker` service mounts it, at `/run/secrets/openai_api_key`. The adapter
reads the key from that file. The key MUST NOT go in Git, logs, archives,
prompts, or the browser bundle.

## Options considered

1. Keep a key file outside the repository and its path in `.env`. This keeps
   the key out of the source folder, but a grader must create a file, set its
   mode, and enter an absolute path.
2. Pass the key to the containers as an environment variable. The key would
   then appear in the container environment and in `docker inspect`.
3. Read the key from `.env` into a Compose secret. Chosen. The key is not in
   the container environment, and `docker compose config` shows only the
   variable name.

## Reason

The owner chose this on 2026-11-07 because one line in `.env` is the easiest
setup for the course grader. `.env` already holds other local secrets, for
example `FEWIA_USDA_FDC_KEY`.

## Consequences

- Git ignores `.env`. A copy of the whole source folder still includes it.
  Make a source ZIP with `git archive --format=zip -o fewia.zip HEAD`, which
  leaves out ignored files.
- The operator MUST NOT show `.env` on a screen share.
- Docker Compose 2.23 or later is a prerequisite for secrets that read an
  environment variable.
- The benchmark CLI runs on the host and still reads
  `FEWIA_OPENAI_API_KEY_FILE`.
