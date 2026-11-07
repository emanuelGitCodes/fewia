.PHONY: up up-bedrock up-offline

up:
	bash infra/openai/compose-up.sh

up-bedrock:
	docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml up -d --build

up-offline:
	docker compose -f compose.yaml up -d --build
