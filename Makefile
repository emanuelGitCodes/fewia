.PHONY: up up-kroger-live up-tools

up:
	bash infra/openai/compose-up.sh

up-kroger-live:
	bash infra/openai/compose-up.sh --kroger-live

up-tools:
	bash infra/openai/compose-up.sh --tools
