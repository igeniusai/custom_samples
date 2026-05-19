from fastapi import APIRouter
from pydantic import BaseModel

from app import process as proc
from app.config import load_config, save_config

router = APIRouter()


class UpdateRequest(BaseModel):
    domyn_api_key: str | None = None
    channel_id: str | None = None
    space_id: str | None = None
    platform_base_url: str | None = None
    vllm_api_key: str | None = None
    vllm_base_url: str | None = None
    vllm_model: str | None = None


@router.post("/update", tags=["agent"])
async def update(body: UpdateRequest) -> dict:
    config = load_config()
    patches = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = config.model_copy(update=patches)
    save_config(updated)
    return {"status": "ok", "config": updated.model_dump()}


@router.post("/start", tags=["agent"])
async def start() -> dict:
    return proc.start()


@router.post("/stop", tags=["agent"])
async def stop() -> dict:
    return proc.stop()


@router.get("/status", tags=["agent"])
async def status() -> dict:
    return proc.status()
