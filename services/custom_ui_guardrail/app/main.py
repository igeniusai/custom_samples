"""
FastAPI application — all HTTP concerns live here.

Business logic is fully delegated to routers and judge.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import input_guardrail, output_guardrail

app = FastAPI(
    title="Dual Judge Guardrail",
    version="0.1.0",
    description=(
        "Two independent LLM-based guardrail hooks (input + output) "
        "with admin UI and verdict history."
    ),
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(input_guardrail.router)
app.include_router(output_guardrail.router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
