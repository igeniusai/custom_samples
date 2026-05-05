# README

A minimal template for containerizing and deploying one or more services — locally with Docker Compose or to a Kubernetes cluster with Helm.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose` command available)
- [Task](https://taskfile.dev/installation/) for running tasks
- [Helm](https://helm.sh/docs/intro/install/) for cluster deployments

## Project structure

```text
.
├── apps/
│   └── example/          # Reference app (nginx static file server)
│       ├── DOCKERFILE
│       ├── README.md
│       ├── html/
│       └── nginx.conf
├── helm/
│   └── services/         # Helm chart (supports multiple services)
│       ├── Chart.yaml
│       ├── templates/
│       └── values.yaml   # Chart defaults
├── .env                  # Environment variables loaded by Taskfile
├── Compose.yaml
├── Taskfile.yaml
└── values.yaml           # Override values for cluster deploys
```

## Local deployment

### Build and start

```bash
task build
task local:deploy
```

The server will be available at `http://localhost:8080`.

### Stop

```bash
task local:remove
```

### View logs

```bash
docker compose logs -f
```

## Cluster deployment

Requires a running Kubernetes cluster (e.g. Docker Desktop with Kubernetes enabled).

### Build the image

The cluster uses the locally built image (`imagePullPolicy: Never`), so build it first:

```bash
task build
```

### Deploy

```bash
task cluster:deploy
```

This installs (or upgrades) the Helm release (`services`) into the `test` namespace, creating it if it does not exist. Each entry in the `services` list in `values.yaml` produces one Deployment and one LoadBalancer Service. On Docker Desktop the external IP is `localhost`.

```bash
# override the namespace
task cluster:deploy namespace=my-namespace
```

### Test

```bash
task local:test
```

### Uninstall

```bash
task cluster:remove
# or manually:
helm uninstall services --namespace test
```

## Multi-service deployments

`values.yaml` accepts a list of services. Each entry produces its own Deployment and LoadBalancer:

```yaml
services:
  - name: frontend
    image:
      repository: frontend
      tag: "latest"
      pullPolicy: Never
    containerPort: 80
    port: 8080

  - name: api
    image:
      repository: api
      tag: "latest"
      pullPolicy: Never
    containerPort: 3000
    port: 3000
```

## Using this repo as a template

The [apps/example/](apps/example/) directory contains a working `nginx` static file server that shows how to structure an app for this repo. See [apps/example/README.md](apps/example/README.md) for details. To ship your own service:

1. **Replace the app** — swap out the contents of `apps/example/` (or add a new directory under `apps/`) with your own application code and configuration.
2. **Update the Dockerfile** — point the `COPY` instructions in [apps/example/DOCKERFILE](apps/example/DOCKERFILE) at your app's files.
3. **Adjust Helm values** — edit [values.yaml](values.yaml) to match your service's port, image name, and any other deployment settings.
4. **Rebuild** — run `task build` after any change to produce a fresh image.
