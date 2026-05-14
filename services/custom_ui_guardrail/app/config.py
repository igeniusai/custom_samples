"""
Models, state and singletons shared across the app.

GuardrailState is kept in-memory.  Configuration (policy, LLM provider) is
also persisted to a JSON file as a best-effort fallback:
  - On startup  → loaded from disk if the file exists and is readable.
  - On update   → written to disk; any I/O error is logged and silently ignored.

Verdict history is NOT persisted (runtime data only).
"""

import json
import logging
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Root of the project (one level above this package).
BASE_DIR = Path(__file__).parent.parent

TEMPLATES_DIR = BASE_DIR / "templates"


# ---------------------------------------------------------------------------
# App settings  (reads from environment variables / .env file)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    guardrail_settings_dir: Path = BASE_DIR / "data"

    model_config = {"env_file": BASE_DIR / ".env", "extra": "ignore"}


settings = Settings()

# ---------------------------------------------------------------------------
# Policy default
# ---------------------------------------------------------------------------

DEFAULT_POLICY = """
1. Mask all PIIs with the string "[PII:<input pii type>]", e.g. "My email is [PII:email]". Mask the following PII types:
\t- Name/Surname
\t- Email
\t- Phone number
\t- Address
\t- Credit card number
\t- Social security number
\t- Date of birth
\t- Salary
\t- IBAN
2. Block any content that contains profanity, hate speech, or adult content.
3. Block any content containing or requesting medical advice.
4. Block any content that doesn't comply with all applicable laws and regulations, including data protection and privacy laws.
"""

# ---------------------------------------------------------------------------
# Verdict / judge models
# ---------------------------------------------------------------------------


class Verdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class JudgeVerdict(BaseModel):
    verdict: Verdict
    reason: str
    output: str


# ---------------------------------------------------------------------------
# Per-guardrail state
# ---------------------------------------------------------------------------


class GuardrailState(BaseSettings):
    policy: str | None = DEFAULT_POLICY
    model_name: str | None = None
    url: str | None = None
    api_key: str | None = None
    verdict_history: dict[str, list[JudgeVerdict]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Persistence helpers  (best-effort — never raise)
# ---------------------------------------------------------------------------

# Fields persisted to disk. verdict_history is in-memory only.
_PERSIST_FIELDS = ("policy", "model_name", "url", "api_key")


def save_state(state: GuardrailState, name: str) -> None:
    """Write config fields to <settings.guardrail_settings_dir>/<name>.json.  Silently no-ops on any error."""
    try:
        settings.guardrail_settings_dir.mkdir(parents=True, exist_ok=True)
        path = settings.guardrail_settings_dir / f"{name}.json"
        snapshot = {k: getattr(state, k) for k in _PERSIST_FIELDS}
        path.write_text(json.dumps(snapshot, indent=2))
        logger.debug("[config] saved %s → %s", name, path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[config] could not save %s to disk: %s", name, exc)


def load_state(name: str) -> dict:
    """Read config fields from <settings.guardrail_settings_dir>/<name>.json.  Returns {} on any error."""
    try:
        path = settings.guardrail_settings_dir / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text())
            logger.info("[config] loaded %s from %s", name, path)
            return {k: v for k, v in data.items() if k in _PERSIST_FIELDS}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[config] could not load %s from disk: %s", name, exc)
    return {}


# ---------------------------------------------------------------------------
# Module-level singletons — one per guardrail, pre-loaded from disk.
# ---------------------------------------------------------------------------

input_state = GuardrailState(**load_state("input_guardrail"))
output_state = GuardrailState(**load_state("output_guardrail"))
