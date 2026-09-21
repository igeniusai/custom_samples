import logging
import sys
from typing import List, Optional

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from app.store import PushTokenStore, TOKEN_HEADER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(levelname)s: [%(funcName)s] %(message)s"))
logger.addHandler(stream_handler)

app = FastAPI(
    title="push-token-capture",
    description="Captures the push token agents-service hands to a REST tool, for the QA parts suites.",
)

# In memory, so the service has to stay on a single replica — see PushTokenStore.
push_token_store = PushTokenStore()


class CaptureResult(BaseModel):
    captured: bool
    conversation_id: Optional[str] = None
    # Only filled in when nothing was captured: the names (never the values) of the headers that
    # did arrive, so a test can see what the platform actually sent.
    seen_headers: List[str] = []


class CapturedToken(BaseModel):
    token: str
    tool_name: Optional[str] = None
    message_id: Optional[str] = None
    exp: Optional[int] = None
    captured_at: int


@app.get("/", tags=["ops"])
async def root() -> dict[str, str]:
    """The application gateway probes the root to decide the backend is up, so this has to
    answer 200 even though the service does its work elsewhere."""
    return {"status": "ok", "service": "push-token-capture"}


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Named by the ingress as health-probe-path, alongside the root probe above."""
    return {"status": "ok", "service": "push-token-capture"}


@app.api_route("/push-token/capture", methods=["GET", "POST"], response_model=CaptureResult, tags=["push-token"])
async def capture(request: Request):
    """Target of the canvas REST tool: pockets the token agents-service sent with the call.

    Answers 200 whatever happens. It is standing in for a tool, and a tool that fails is a turn
    that derails — the test would then be debugging the agent instead of the capture. `captured`
    is where the truth is.
    """
    token = request.headers.get(TOKEN_HEADER)
    if not token:
        logger.warning(f"capture: no {TOKEN_HEADER} header on the call")
        return CaptureResult(captured=False, seen_headers=sorted(request.headers.keys()))

    payload = push_token_store.put(token)
    if payload is None:
        logger.warning("capture: the header is there but does not read as a token")
        return CaptureResult(captured=False, seen_headers=sorted(request.headers.keys()))

    # The token is a credential: log that one arrived and who for, never its value.
    logger.info(
        f"capture: stored a token for conversation {payload['conversation_id']} "
        f"(tool {payload.get('tool_name')})"
    )
    return CaptureResult(captured=True, conversation_id=payload["conversation_id"])


@app.get("/push-token/{conversation_id}", response_model=CapturedToken, responses={404: {}}, tags=["push-token"])
def read(conversation_id: str, response: Response):
    """Hands the captured token to the test. 404 until the agent has called the tool, so the test
    can poll rather than guess how long the turn takes to get there."""
    entry = push_token_store.get(conversation_id)
    if entry is None:
        response.status_code = 404
        return response
    logger.info(f"read: serving the token for conversation {conversation_id}")
    return CapturedToken(**entry)
