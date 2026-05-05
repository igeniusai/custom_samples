# README

Deploy a service quick and dirty.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Compose v2 (`docker compose` command available)

## Usage

### Build and start

```bash
docker compose up --build
```

The server will be available at `http://localhost:8080`.

### Start in detached mode (background)

```bash
docker compose up --build -d
```

### Stop

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f
```

## Customization

- Replace files in [html/](html/) with your static assets.
- Edit [nginx.conf](nginx.conf) to adjust routing, proxying, or other server settings.
- Rebuild after any change with `docker compose up --build`.
