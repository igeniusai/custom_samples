# README

A template for containerizing and deploying one or more services to a Kubernetes cluster using the **domyn CLI**.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Helm](https://helm.sh/docs/intro/install/) for cluster deployments
- [kubectl](https://kubernetes.io/docs/tasks/tools/) for cluster operations
- [pipx](https://pipx.pypa.io/stable/installation/) to install the domyn CLI
- [Task](https://taskfile.dev/installation/) *(optional)* for CLI lifecycle shortcuts

See [PREREQUISITE.md](PREREQUISITE.md) for full setup instructions including registry configuration and cluster options.

---

## Installing the domyn CLI

```bash
task domyn-cli:install
```

Or without Task:

```bash
pipx install -e ./domyn-cli/
```

Verify the installation:

```bash
domyn --version
```

See [domyn-cli/README.md](domyn-cli/README.md) for the full CLI reference.

---

## Project structure

```text
.
├── services/
│   ├── example1/          # example service — contains Dockerfile + values.yaml
│   ├── example2/          # example service — contains Dockerfile + values.yaml
│   └── ...                # add your own service folders here
├── kubernetes/
│   ├── charts/
│   │   └── services/      # Helm chart used by `domyn deploy`
│   │       ├── Chart.yaml
│   │       ├── templates/
│   │       └── values.yaml
│   └── values.*.yaml      # shared override values files
├── domyn-cli/             # domyn CLI source
│   ├── domyn/main.py
│   └── README.md
├── config.domyn.yaml      # domyn CLI configuration (read by all commands)
└── Taskfile.yaml          # CLI lifecycle shortcuts (install / update / remove)
```

---

## Configuration

All domyn commands read `config.domyn.yaml` from the current working directory.

```yaml
services:
  path: ./services/

containers:
  platform: linux/amd64   # optional — forwarded to docker build as --platform

registries:
  - eu.gcr.io/my-registry

dns:
  postfix: .example.com   # optional — appended to all ingress hosts

helm:
  chart: ./kubernetes/charts/services
  namespace: production
  values_files:           # optional — extra values files merged after service values
    - ./kubernetes/values.base.yaml

kubernetes:
  context: my-cluster-context
```

---

## Quick start

```bash
# 1. Install the CLI
task domyn-cli:install

# 2. List available services
domyn services

# 3. Build and push an image
domyn build my-service --tag v1.0.0
domyn push  my-service --tag v1.0.0

# 4. Deploy to the cluster
domyn deploy my-service
```

---

## Workflow

### Build

Builds the Docker image for a service. The `Dockerfile` must exist inside `<services.path>/<service>/`.

```bash
domyn build <service>
domyn build <service> --tag v1.2.3
```

### Push

Tags the local image and pushes it to every registry listed in `config.domyn.yaml`.

```bash
domyn push <service>
domyn push <service> --tag v1.2.3
```

### Deploy

Deploys a service to Kubernetes via Helm. Uses the release name `<service>` and merges values in this order:

1. `<services.path>/<service>/values.yaml` — service-specific values
2. Files listed under `helm.values_files` — shared/environment overrides

```bash
domyn deploy <service>
```

### Remove

Uninstalls the Helm release from the cluster.

```bash
domyn remove <service>
```

---

## Configuring deployments

Each service folder must contain a `values.yaml` that configures how it is deployed. The full schema is documented in [`kubernetes/charts/services/values.yaml`](kubernetes/charts/services/values.yaml).

### Minimal example

```yaml
services:
  - name: my-service
    image:
      repository: my-service
      tag: "latest"
      pullPolicy: Always
    expose:
      - name: external
        type: LoadBalancer
        ports:
          - port: 8080
            targetPort: 80
            name: http
            protocol: TCP
```

### With ingress

```yaml
ingress:
  enabled: true
  host: my-service
  ingressClass: nginx
  tls:
    enabled: true
    secretName: my-service-tls
```

When `dns.postfix` is set in `config.domyn.yaml`, the final host becomes `<host>.<postfix>` (e.g. `my-service.example.com`).

---

## TLS / HTTPS

Scripts for generating self-signed certificates live under `scripts/tls/`. See [scripts/tls/README.md](scripts/tls/README.md) for full documentation.

### 1. Generate certificates

```bash
cd scripts/tls
./create_certs.sh --cert-name myservice --cert-cn myservice.local --cert-san DNS:myservice.local
```

### 2. Trust the CA on macOS

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  scripts/tls/certs/ca.crt
```

### 3. Load the Secret into the cluster

```bash
./scripts/tls/cluster_tls.sh \
  --cert-name myservice \
  --secret-name myservice-tls \
  --namespace production
```

### 4. Enable TLS in the service values.yaml

```yaml
ingress:
  enabled: true
  host: myservice
  tls:
    enabled: true
    secretName: myservice-tls
```

Then redeploy:

```bash
domyn deploy myservice
```

---

## Task reference

| Task | Description |
| --- | --- |
| `task domyn-cli:install` | Install the domyn CLI via pipx |
| `task domyn-cli:update` | Reinstall to pick up local code changes |
| `task domyn-cli:remove` | Uninstall the domyn CLI |
