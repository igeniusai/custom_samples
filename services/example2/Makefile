.PHONY: install run run-dev expose docker-build docker-run docker-run-exposed

install:
	uv sync --dev

lint-fix:
	uv run ruff check --fix .

run:
	uv run python -m mcpesg.main

run-dev:
	uv run python -m mcpesg.main_dev

SERVEO_SUBDOMAIN ?= mcp

expose:
	chmod 400 ./serveo_key
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./serveo_key -R $(SERVEO_SUBDOMAIN):80:localhost:8080 serveo.net

expose-random:
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -R 80:localhost:8080 serveo.net

docker-build:
	docker build -t mcpesg .

docker-run: docker-build
	docker run --rm -p 8080:8080 mcpesg

docker-run-exposed: docker-build
	docker run --rm -p 8080:8080 \
		-e EXPOSE_SERVEO=true \
		-e SERVEO_SUBDOMAIN=$(SERVEO_SUBDOMAIN) \
		-e BASE_EXPOSED_URL=https://$(SERVEO_SUBDOMAIN).serveousercontent.com \
		mcpesg

docker-run-exposed-random: docker-build
	docker run --rm -p 8080:8080 -e EXPOSE_SERVEO=true -e SERVEO_RANDOM_SUBDOMAIN=true mcpesg
