import json
from pathlib import Path

from pydantic import BaseModel

_DATA_DIR = Path("data")
_CONFIG_FILE = _DATA_DIR / "config.json"


class AgentConfig(BaseModel):
    domyn_api_key: str = ""
    channel_id: str = ""
    space_id: str = ""
    platform_base_url: str = ""
    vllm_api_key: str = ""
    vllm_base_url: str = ""
    vllm_model: str = ""


def load_config() -> AgentConfig:
    if _CONFIG_FILE.exists():
        return AgentConfig.model_validate_json(_CONFIG_FILE.read_text())
    return AgentConfig()


def save_config(config: AgentConfig) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _CONFIG_FILE.write_text(config.model_dump_json(indent=2))
