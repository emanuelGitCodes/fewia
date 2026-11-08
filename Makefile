.PHONY: up up-kroger-live

up:
	bash infra/openai/compose-up.sh

up-kroger-live:
	bash infra/openai/compose-up.sh --kroger-live
