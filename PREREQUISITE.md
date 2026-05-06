# Prerequisites

This document describes everything that must be installed, configured, and in place before using this project to build and deploy services.

---

## Required Tools

| Tool | Purpose | Minimum Version |
| ---- | ------- | --------------- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Build images and run local containers | 4.x |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Interact with Kubernetes clusters | 1.28+ |
| [Helm](https://helm.sh/docs/intro/install/) | Deploy the Helm chart to a cluster | 3.x |
| [Task](https://taskfile.dev/installation/) | Run automation tasks (`Taskfile.yaml`) | 3.x |
| [OpenSSL](https://openssl.org) | Generate TLS certificates (HTTPS only) | 3.x |

Verify your installations:

```bash
docker --version
kubectl version --client
helm version
task --version
openssl version
```

---

## Container Registry

A container registry is required to store the Docker images that the cluster will pull.

- The registry can be any Docker-compatible registry (Docker Hub, GitHub Container Registry, a private registry, etc.).
- Configure the registry prefix in the `.env` file at the project root:

```dotenv
# .env
registry1="your-registry/your-org/"   # include the trailing slash
```

This value is interpolated into `Compose.yaml` image references and used as the image source when deploying to the cluster.

### Allowing the Cluster to Pull Images

The Kubernetes cluster must be able to authenticate with the registry. For **private registries**, create an `imagePullSecret` and reference it in your values file:

```bash
kubectl create secret docker-registry regcred \
  --docker-server=<your-registry> \
  --docker-username=<username> \
  --docker-password=<password> \
  --namespace=<namespace>
```

Then add it to `kubernetes/values.auto.yaml` (or your values override file):

```yaml
imagePullSecrets:
  - name: regcred
```

For **public registries**, no pull secret is needed.

---

## Kubernetes Cluster

A running Kubernetes cluster is required for all `cluster:*` tasks.

### Option A — Docker Desktop (Local, Recommended for Development)

Docker Desktop includes a built-in single-node Kubernetes cluster. This is the easiest way to test the full deployment flow locally without a remote cluster.

1. Open **Docker Desktop → Settings → Kubernetes**
2. Enable **Kubernetes** and click **Apply & Restart**
3. Once started, the context `docker-desktop` is automatically added to your kubeconfig

Verify the context is active:

```bash
kubectl config use-context docker-desktop
kubectl get nodes
```

> When using Docker Desktop, set `pullPolicy: Never` for each service in your values file so Kubernetes uses the locally built image instead of pulling from a registry.
>
> ```yaml
> services:
>   - name: example
>     image:
>       pullPolicy: Never
> ```

### Option B — Remote Cluster

Point `kubectl` at your remote cluster by configuring the context:

```bash
# Merge an existing kubeconfig
export KUBECONFIG=~/.kube/config:/path/to/cluster-kubeconfig.yaml
kubectl config use-context <your-cluster-context>
```

Confirm the cluster is reachable:

```bash
kubectl cluster-info
kubectl get nodes
```

For remote clusters, images must be pushed to the registry before deploying:

```bash
task build          # builds images
docker push <registry>/<image>:<tag>   # push manually, or configure CI
task cluster:deploy
```

---

## Nginx Ingress Controller

HTTP/HTTPS routing via Ingress requires the nginx Ingress controller to be installed in the cluster. This is a one-time setup per cluster:

```bash
task cluster:nginx_ingress
```

This applies the official nginx Ingress controller manifest. Skip this step if your cluster already has an Ingress controller.

---

## TLS / HTTPS (Optional)

HTTPS is supported through self-signed certificates generated locally and loaded into the cluster as a Kubernetes TLS Secret.

### Requirements

- `openssl` must be installed
- `kubectl` must be pointed at the target cluster

### Setup Steps

1. **Generate certificates** (from the `scripts/tls/` directory):

   ```bash
   cd scripts/tls
   ./create_certs.sh --cert-cn myservice.local --cert-san DNS:myservice.local
   ```

2. **Trust the CA on your local machine** (macOS):

   ```bash
   sudo security add-trusted-cert -d -r trustRoot \
     -k /Library/Keychains/System.keychain certs/ca.crt
   ```

3. **Add the hostname to `/etc/hosts`**:

   ```text
   127.0.0.1   myservice.local
   ```

4. **Load the certificate into the cluster**:

   ```bash
   task cluster:tls_secret
   # or directly:
   ./cluster_tls.sh --secret-name tls-secret --namespace test
   ```

5. **Enable TLS in your values file**:

   ```yaml
   services:
     - name: example
       ingress:
         enabled: true
         host: myservice.local
         tls:
           enabled: true
           secretName: tls-secret
   ```

See [scripts/tls/README.md](scripts/tls/README.md) for full certificate configuration options.

---

## Local Machine Summary Checklist

- [ ] Docker Desktop installed and running
- [ ] `kubectl` installed and configured with the target cluster context
- [ ] `helm` installed
- [ ] `task` installed
- [ ] `.env` updated with the correct registry prefix
- [ ] Registry pull credentials configured in the cluster (if using a private registry)
- [ ] Nginx Ingress controller installed in the cluster
- [ ] (HTTPS only) `openssl` installed
- [ ] (HTTPS only) TLS certificates generated and loaded into the cluster
