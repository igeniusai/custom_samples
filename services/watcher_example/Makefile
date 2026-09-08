.PHONY: install dev build run logs stop clean

install:
	uv sync --dev

dev:
	uv run uvicorn watcher_example:app --reload --port 8089

build:
	docker build -t watcher-example .

run:
	docker compose up -d

logs:
	docker compose logs -f

stop:
	docker compose down

clean:
	docker compose down --rmi local --volumes
