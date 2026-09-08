from pydantic import BaseModel


class HookRequest(BaseModel):
    current_event: dict | None = None
    interaction_history: list[dict] | None = None
    interaction_context: dict | None = None


class HookResult(BaseModel):
    success: bool = True
    break_execution: bool = False
    modified_event: dict | None = None 
