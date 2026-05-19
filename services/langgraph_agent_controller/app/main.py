from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import agent

app = FastAPI(
    title="LangGraph Agent Controller",
    version="0.1.0",
    description="Configure, start, and stop the langgraph agent expose process.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent.router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
