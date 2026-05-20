# Custom Samples - Deployment

A template for containerizing and deploying one or more services — locally with Docker Compose or to a Kubernetes cluster with Helm.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose` command available)
- [Task](https://taskfile.dev/installation/) for running tasks
- [Helm](https://helm.sh/docs/intro/install/) for cluster deployments
- [kubectl](https://kubernetes.io/docs/tasks/tools/) for cluster operations

See [PREREQUISITE.md](PREREQUISITE.md) for full setup instructions including registry configuration, cluster options, and TLS setup.

## Project structure

```text
.
├── services/
│   ├── example1/                          # nginx static file server
│   ├── example2/                          # MCP ESG investment demo (FastAPI + FastMCP)
│   ├── langgraph_agent_example/           # LangGraph agent example
│   ├── langgraph_deterministic_graph_example/ # LangGraph deterministic graph example
│   ├── custom_ui_guardrail/               # Guardrail with custom admin UI
│   └── minimal_guardrail/                 # Minimal guardrail example
├── kubernetes/
│   ├── charts/
│   │   └── services/         # Helm chart
│   │       ├── Chart.yaml
│   │       ├── templates/
│   │       └── values.yaml   # Chart defaults
│   ├── manifest/             # Raw Kubernetes manifests (e.g. secrets)
│   ├── values.test.yaml      # Override values for local cluster deploys
│   └── values.blueprint.yaml # Override values for production/remote cluster deploys
├── scripts/
│   ├── example/
│   │   └── pull.sh           # Update example service source code
│   └── tls/                  # TLS certificate generation and cluster secret management
│       ├── create_certs.sh
│       ├── cluster_tls.sh
│       ├── Taskfile.yaml
│       └── certs/
├── .env                      # Environment variables loaded by Taskfile
├── Compose.yaml
├── Taskfile.yaml
└── PREREQUISITE.md           # Full setup and prerequisites guide
```

## Quick start

### Local

```bash
task build
task local:deploy
# visit http://localhost:8080
```

Or without Task:

```bash
docker compose build
docker compose up -d
# visit http://localhost:8080
```

### Cluster (Docker Desktop)

```bash
task build
task cluster:nginx_ingress   # first time only — installs the nginx Ingress controller
task cluster:deploy
```

Or without Task:

```bash
docker compose build
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
helm upgrade --install services ./kubernetes/charts/services --values kubernetes/values.test.yaml --namespace test --create-namespace --kube-context docker-desktop
```

---

## Local deployment

### Build and start

```bash
task build
task local:deploy
```

Or without Task:

```bash
docker compose build
docker compose up -d
```

The server will be available at `http://localhost:8080`.

### Stop

```bash
task local:remove
```

Or without Task:

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f
```

### Test

```bash
task local:test
```

Or without Task:

```bash
curl -v --resolve "localhost:8080:127.0.0.1" "http://localhost:8080"
```

Sends a `curl` request to `localhost:8080` and prints the response.

---

## Cluster deployment

Requires a running Kubernetes cluster (e.g. Docker Desktop with Kubernetes enabled).

### Install the Nginx Ingress controller (first time only)

```bash
task cluster:nginx_ingress
```

Or without Task:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/cloud/deploy.yaml
```

This deploys the nginx Ingress controller to the cluster. Only needed once per cluster.

### Build the image

The cluster uses the locally built image (`imagePullPolicy: Never`), so build it first:

```bash
task build
```

Or without Task:

```bash
docker compose build
```

### Deploy

```bash
task cluster:deploy
```

Or without Task:

```bash
helm upgrade --install services ./kubernetes/charts/services --values kubernetes/values.test.yaml --namespace test --create-namespace --kube-context docker-desktop
```

Installs (or upgrades) the Helm release `services` into the `test` namespace, creating it if it does not exist. The task will prompt for confirmation before applying, showing the active context and namespace.

Override the namespace, release name, or kubectl context:

```bash
task cluster:deploy namespace=staging
task cluster:deploy namespace=staging helm_release_name=my-release
task cluster:deploy context=my-aks-cluster namespace=production
# without Task:
helm upgrade --install my-release ./kubernetes/charts/services --values kubernetes/values.test.yaml --namespace staging --create-namespace --kube-context my-aks-cluster
```

### Uninstall

```bash
task cluster:remove
```

Or without Task:

```bash
helm uninstall services --namespace test
```

---

## Configuring deployments

All deployments are driven by `kubernetes/values.test.yaml`. The chart schema is documented in `kubernetes/charts/services/values.yaml`.

### Service entry structure

Each entry in the `services` list produces one **Deployment** and one or more **Kubernetes Service** objects.

```yaml
services:
  - name: api
    image:
      registry: ghcr.io/myorg   # omit for local images
      repository: api
      tag: "1.0.0"
      pullPolicy: IfNotPresent
    expose:
      - name: external
        type: LoadBalancer
        ports:
          - port: 8080       # port on the Kubernetes Service
            targetPort: 80   # container port
            name: http
            protocol: TCP
    ingress:
      enabled: false
      host: ""
      ingressClass: nginx
      portName: http
      exposeName: ""         # defaults to the first expose entry
      tls:
        enabled: false
        secretName: ""
```

### Multiple Kubernetes Services per deployment

A single deployment can be exposed through several Service objects — for example an external `LoadBalancer` and an internal `ClusterIP`:

```yaml
services:
  - name: api
    image:
      repository: api
      tag: "latest"
    expose:
      - name: external
        type: LoadBalancer
        ports:
          - port: 8080
            targetPort: 80
            name: http
            protocol: TCP
      - name: internal
        type: ClusterIP
        ports:
          - port: 80
            targetPort: 80
            name: http
            protocol: TCP
```

Each expose entry creates a Service named `<release>-<app>-<expose.name>`.

### Multiple deployments

Add more entries to the `services` list; each produces its own independent Deployment:

```yaml
services:
  - name: frontend
    image:
      repository: frontend
      tag: "latest"
    expose:
      - name: external
        type: LoadBalancer
        ports:
          - port: 3000
            targetPort: 3000
            name: http
            protocol: TCP

  - name: api
    image:
      repository: api
      tag: "latest"
    expose:
      - name: external
        type: LoadBalancer
        ports:
          - port: 8080
            targetPort: 8080
            name: http
            protocol: TCP
```

### Ingress

Enable an nginx Ingress resource to route HTTP or HTTPS traffic by hostname:

```yaml
ingress:
  enabled: true
  host: myservice.local
  ingressClass: nginx
  portName: http       # must match a port name in expose[*].ports
  exposeName: external # which expose entry to use as backend; defaults to first
```

For HTTPS, also enable TLS (the Secret must exist before deploying — see [TLS](#tls--https)):

```yaml
ingress:
  enabled: true
  host: myservice.local
  tls:
    enabled: true
    secretName: myservice-tls
```

---

## TLS / HTTPS

Scripts for generating self-signed certificates (local development only) live under `scripts/tls/`. See [scripts/tls/README.md](scripts/tls/README.md) for full documentation.

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

Then open **Keychain Access → System → Certificates**, find the CA, and confirm SSL is set to *Always Trust*. Fully restart your browser afterwards.

### 3. Add a hosts entry

```bash
echo "127.0.0.1 myservice.local" | sudo tee -a /etc/hosts
```

### 4. Load the Secret into the cluster

```bash
./scripts/tls/cluster_tls.sh \
  --cert-name myservice \
  --secret-name myservice-tls \
  --namespace test
```

Or use the task shortcut (uses defaults from `cluster_tls.sh`):

```bash
task cluster:tls_secret
```

### 5. Enable TLS in values

Set `ingress.tls.enabled: true` and `ingress.tls.secretName` in `kubernetes/values.test.yaml`:

```yaml
ingress:
  enabled: true
  host: myservice.local
  tls:
    enabled: true
    secretName: myservice-tls
```

Then redeploy:

```bash
task cluster:deploy
```

---

## Deployed services

After a successful `task cluster:deploy` the following endpoints are available (assuming the default `kubernetes/values.test.yaml` and `/etc/hosts` entries pointing `127.0.0.1` at each hostname):

| Service | Host | Notable endpoints |
| --- | --- | --- |
| example1 | `https://test1.local` | Static HTML page |
| example2 | `https://test2.local` | MCP investment demo |

### OpenAPI (example2)

The example2 service exposes an interactive OpenAPI page at:

```text
https://test2.local/docs
```

Open it in a browser after deploying to explore the available API endpoints.

---

## Task reference

| Task | Description |
| --- | --- |
| `task build` | Build all Docker images via `docker compose build` |
| `task update` | Update example service source code |
| `task local:deploy` | Start the stack locally with Docker Compose |
| `task local:remove` | Stop and remove the local stack |
| `task local:test` | Curl `localhost:8080` to verify the local deployment |
| `task cluster:deploy` | Install or upgrade the Helm release (prompts for confirmation) |
| `task cluster:remove` | Uninstall the Helm release |
| `task cluster:nginx_ingress` | Deploy the nginx Ingress controller (first time only) |
| `task cluster:tls_secret` | Create the TLS Secret in the cluster |

---

## Using this repo as a template

The [services/example1/](services/example1/) directory contains a working nginx static file server and [services/example2/](services/example2/) contains a FastAPI + MCP service. See their respective READMEs for details. To ship your own service:

1. **Add your app** — create a new directory under `services/` with your application code and a `DOCKERFILE`.
2. **Update Compose.yaml** — point the `build.context` at your new directory and set the `image` name.
3. **Update `kubernetes/values.test.yaml`** — add an entry to the `services` list with your image, ports, and any ingress or TLS configuration.
4. **Rebuild** — run `task build` after any code change to produce a fresh image.
