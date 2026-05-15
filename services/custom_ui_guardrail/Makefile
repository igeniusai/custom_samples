.PHONY: install dev build run logs stop clean

install:
	uv sync --dev

dev:
	uv run uvicorn guardrail_custom_ui_blueprint:app --reload --port 8080

build:
	docker build -t guardrail-custom-ui .

run:
	docker compose up -d

logs:
	docker compose logs -f

stop:
	docker compose down

clean:
	docker compose down --rmi local --volumes
