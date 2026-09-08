import logging

from fastapi import FastAPI

from app.routers import passthrough_hooks, watch_event

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Watcher Example",
    version="0.1.0",
    description="Minimal blueprint that logs incoming hook events and acknowledges them.",
)

app.include_router(watch_event.router)
app.include_router(passthrough_hooks.router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["ops"])
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "watcher-example"}
