.PHONY: help build build-wheel up down logs shell clean

help:
	@echo "Targets:"
	@echo "  build-wheel   Build the wheel file for domyn-agents"
	@echo "  build   Build the docker image"
	@echo "  up      docker compose up -d"
	@echo "  down    docker compose down"
	@echo "  logs    Tail container logs"
	@echo "  shell   Exec a bash shell into the running container"
	@echo "  clean   docker compose down -v --rmi local"


DOMYN_AGENT_PATH ?=../../../domyn-agents
build-wheel:
	rm $(DOMYN_AGENT_PATH)/dist/*.whl
	$(MAKE) -C $(DOMYN_AGENT_PATH) build-wheel
	cp $(DOMYN_AGENT_PATH)/dist/*.whl ./wheels/

build: build-wheel
	docker compose build

up:
	docker compose up -d
	@echo "Worker started — check 'make logs' for the registered tool list."

down:
	docker compose down

logs:
	docker compose logs -f hermes-platform-gateway

shell:
	docker compose exec hermes-platform-gateway bash

clean:
	docker compose down -v --rmi local
