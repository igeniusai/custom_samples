# README

A template for containerizing and deploying one or more services — locally with Docker Compose or to a Kubernetes cluster with Helm.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose` command available)
- [Task](https://taskfile.dev/installation/) for running tasks
- [Helm](https://helm.sh/docs/intro/install/) for cluster deployments
- [kubectl](https://kubernetes.io/docs/tasks/tools/) for cluster operations

## Project structure

```text
.
├── services/
│   └── example/              # Reference app (nginx static file server)
│       ├── DOCKERFILE
│       ├── README.md
│       ├── html/
│       └── nginx.conf
├── kubernetes/
│   ├── charts/
│   │   └── services/         # Helm chart
│   │       ├── Chart.yaml
│   │       ├── templates/
│   │       └── values.yaml   # Chart defaults
│   └── values.test.yaml      # Override values for cluster deploys
├── scripts/
│   └── tls/                  # TLS certificate generation and cluster secret management
│       ├── create_certs.sh
│       ├── cluster_tls.sh
│       ├── Taskfile.yaml
│       └── certs/
├── .env                      # Environment variables loaded by Taskfile
├── Compose.yaml
└── Taskfile.yaml
```

## Quick start

### Local

```bash
task build
task local:deploy
# visit http://localhost:8080
```

### Cluster (Docker Desktop)

```bash
task build
task cluster:nginx_ingress   # first time only — installs the nginx Ingress controller
task cluster:deploy
```

---

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

### Test

```bash
task local:test
```

Sends a `curl` request to `localhost:8080` and prints the response.

---

## Cluster deployment

Requires a running Kubernetes cluster (e.g. Docker Desktop with Kubernetes enabled).

### Install the nginx Ingress controller (first time only)

```bash
task cluster:nginx_ingress
```

This deploys the nginx Ingress controller to the cluster. Only needed once per cluster.

### Build the image

The cluster uses the locally built image (`imagePullPolicy: Never`), so build it first:

```bash
task build
```

### Deploy

```bash
task cluster:deploy
```

Installs (or upgrades) the Helm release `services` into the `test` namespace, creating it if it does not exist. Override the namespace or release name:

```bash
task cluster:deploy namespace=staging
task cluster:deploy namespace=staging helm_release_name=my-release
```

### Uninstall

```bash
task cluster:remove
# or manually:
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

## Task reference

| Task | Description |
| --- | --- |
| `task build` | Build the Docker image via `docker compose build` |
| `task local:deploy` | Start the stack locally with Docker Compose |
| `task local:remove` | Stop and remove the local stack |
| `task local:test` | Curl `localhost:8080` to verify the local deployment |
| `task cluster:deploy` | Install or upgrade the Helm release |
| `task cluster:remove` | Uninstall the Helm release |
| `task cluster:nginx_ingress` | Deploy the nginx Ingress controller (first time only) |
| `task cluster:tls_secret` | Create the TLS Secret in the cluster |

---

## Using this repo as a template

The [services/example/](services/example/) directory contains a working nginx static file server. See [services/example/README.md](services/example/README.md) for details. To ship your own service:

1. **Add your app** — create a new directory under `services/` with your application code and a `DOCKERFILE`.
2. **Update Compose.yaml** — point the `build.context` at your new directory and set the `image` name.
3. **Update `kubernetes/values.test.yaml`** — add an entry to the `services` list with your image, ports, and any ingress or TLS configuration.
4. **Rebuild** — run `task build` after any code change to produce a fresh image.
