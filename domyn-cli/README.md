# domyn CLI

A command-line tool to build, push, and deploy containerized services to a Kubernetes cluster using Docker and Helm.

## Installation

```bash
pipx install -e .
```

After installation the `domyn` binary is available on your `$PATH`.

### Updating

To pick up code changes after pulling the latest version:

```bash
pipx reinstall domyn
```

### Uninstalling

```bash
pipx uninstall domyn
```

---

## Configuration

Every command reads a `config.domyn.yaml` file from the current working directory by default. A different file can be specified with the global `--config-file` flag.

### Full configuration reference

```yaml
# Path to the folder that contains one sub-folder per service.
# Each sub-folder must contain a Dockerfile and, for deploy, a values.yaml.
services:
  path: ./services/

# Container build settings (optional)
containers:
  platform: linux/amd64   # passed as --platform to docker build

# List of registries the images are pushed to.
registries:
  - eu.gcr.io/my-registry

# DNS postfix appended to every ingress host in the Helm chart (optional).
dns:
  postfix: .example.com

# Helm deployment settings
helm:
  chart: ./kubernetes/charts/services   # path or name of the Helm chart
  namespace: production
  values_files:                         # extra values files (optional)
    - ./kubernetes/values.base.yaml
    - ./kubernetes/values.prod.yaml

# Kubernetes context used by both helm deploy and helm uninstall
kubernetes:
  context: my-cluster-context
```

---

## Global options

| Flag | Default | Description |
|------|---------|-------------|
| `--config-file PATH` | `config.domyn.yaml` | Path to the configuration file |
| `--version` / `-v` | — | Print the CLI version and exit |

The `--config-file` flag must appear **before** the subcommand:

```bash
domyn --config-file staging.yaml deploy my-service
```

---

## Commands

### `config`

Checks whether the configuration file can be found and prints its path.

```bash
domyn config
```

---

### `services`

Lists all services that have a `Dockerfile` inside the folder defined by `services.path`.

```bash
domyn services
```

---

### `build`

Builds the Docker image for a service.

```bash
domyn build <service> [--tag TAG]
```

| Argument / Option | Default | Description |
|-------------------|---------|-------------|
| `service` | required | Name of the sub-folder inside `services.path` |
| `--tag` / `-t` | `latest` | Docker image tag |

The image is tagged as `<service>:<tag>`. If `containers.platform` is set in the config, `--platform` is forwarded to `docker build`.

**Examples**

```bash
domyn build my-service
domyn build my-service --tag v1.2.3
domyn --config-file staging.yaml build my-service --tag v1.2.3
```

---

### `push`

Tags the local image and pushes it to every registry listed under `registries`.

```bash
domyn push <service> [--tag TAG]
```

| Argument / Option | Default | Description |
|-------------------|---------|-------------|
| `service` | required | Name of the service (must match a previously built image) |
| `--tag` / `-t` | `latest` | Docker image tag |

For each registry the command runs:
1. `docker tag <service>:<tag> <registry>/<service>:<tag>`
2. `docker push <registry>/<service>:<tag>`

**Examples**

```bash
domyn push my-service
domyn push my-service --tag v1.2.3
```

---

### `deploy`

Deploys a service to Kubernetes using Helm.

```bash
domyn deploy <service>
```

The release name used by Helm is the service name. Values are merged in the following order (last wins):

1. `<services.path>/<service>/values.yaml` — service-specific values
2. Each file listed in `helm.values_files` — shared/environment values

If `dns.postfix` is set, it is forwarded to the chart via `--set dns.postfix=<value>`.

**Examples**

```bash
domyn deploy my-service
domyn --config-file staging.yaml deploy my-service
```

The equivalent Helm command that gets executed:

```bash
helm upgrade --install my-service ./kubernetes/charts/services \
  --values ./services/my-service/values.yaml \
  --values ./kubernetes/values.base.yaml \
  --set dns.postfix=.example.com \
  --namespace production \
  --create-namespace \
  --kube-context my-cluster-context
```

---

### `remove`

Uninstalls a Helm release from the cluster.

```bash
domyn remove <service>
```

**Examples**

```bash
domyn remove my-service
domyn --config-file staging.yaml remove my-service
```

---

## Typical workflow

```bash
# 1. Check the config is readable
domyn config

# 2. See which services are available
domyn services

# 3. Build and push a specific service
domyn build my-service --tag v1.2.3
domyn push my-service --tag v1.2.3

# 4. Deploy to the cluster
domyn deploy my-service

# 5. Tear it down when no longer needed
domyn remove my-service
```
