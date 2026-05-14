"""
Pydantic request models shared across routers.
"""

from pydantic import BaseModel


class GuardrailRequest(BaseModel):
    """Body of every POST Domyn sends to a guardrail hook endpoint."""

    current_event: dict
    interaction_history: list[dict] = []
