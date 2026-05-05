# Nginx example

A minimal `nginx`-based static file server, used as a reference app to demonstrate how to package and deploy a service using this template.

## Structure

```text
apps/example/
├── html/
│   └── index.html      # Static assets served by nginx
└── nginx.conf          # nginx server configuration
```

## How it works

The app runs `nginx` listening on port `80` inside the container, serving static files from `/usr/share/nginx/html`. The root Dockerfile copies both `nginx.conf` and the `html/` directory into the image at build time.

The Compose setup maps host port `8080` → container port `80`, so the app is reachable at `http://localhost:8080` after deployment.

## Customization

**Replace the static content** — edit or add files under `html/`. Any file placed there will be served directly by Nginx.

**Adjust the server behavior** — edit `nginx.conf` to change the listening port, add proxy rules, configure caching, enable `gzip`, etc.

Rebuild the image after any change:

```bash
task build
```

## nginx.conf highlights

| Setting | Value | Notes |
| --- | --- | --- |
| `listen` | `80` | Port exposed inside the container |
| `root` | `/usr/share/nginx/html` | Document root for static files |
| `try_files` | `$uri $uri/ =404` | Serves the file or returns 404 |
| `worker_connections` | `1024` | Max concurrent connections per worker |
