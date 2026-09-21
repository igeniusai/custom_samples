import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app, push_token_store
from app.store import PushTokenStore

TOKEN_HEADER = "x-domyn-push-token"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_token(conversation_id="conv-1", tool_name="capture_push_token", ttl_seconds=3600, **overrides):
    """Builds a token shaped like the one agents-service mints.

    The signature half is never verified here - the store cannot verify it, it has no secret -
    so any filler will do. Only the payload half has to be real.
    """
    payload = {
        "v": 1,
        "space_id": "space-1",
        "conversation_id": conversation_id,
        "user_id": "user-1",
        "tool_name": tool_name,
        "message_id": "message-1",
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
    }
    payload.update(overrides)
    return f"{_b64url(json.dumps(payload).encode())}.{_b64url(b'not-a-real-signature')}"


@pytest.fixture(autouse=True)
def clean_store():
    push_token_store.clear()
    yield
    push_token_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_capture_then_read(client):
    token = make_token(conversation_id="conv-abc")

    captured = client.post("/push-token/capture", headers={TOKEN_HEADER: token})
    assert captured.status_code == 200
    assert captured.json()["captured"] is True

    read = client.get("/push-token/conv-abc")
    assert read.status_code == 200
    body = read.json()
    assert body["token"] == token
    assert body["tool_name"] == "capture_push_token"


def test_capture_accepts_get_too(client):
    """The canvas tool may be configured as either verb, so both capture."""
    token = make_token(conversation_id="conv-get")

    assert client.get("/push-token/capture", headers={TOKEN_HEADER: token}).json()["captured"] is True
    assert client.get("/push-token/conv-get").status_code == 200


def test_capture_ignores_a_body(client):
    """Whatever parameters the agent invents for the tool are none of our business."""
    token = make_token(conversation_id="conv-body")

    captured = client.post(
        "/push-token/capture",
        headers={TOKEN_HEADER: token},
        json={"question": "anything at all"},
    )

    assert captured.json()["captured"] is True


def test_missing_header_still_answers_200_and_names_what_arrived(client):
    """A failed capture must not fail the agent's tool call: it answers 200 and says so.

    The header names it did see are the whole point of the probe - they tell us what
    agents-service actually sends. Names only, never values.
    """
    captured = client.post("/push-token/capture", headers={"x-something-else": "v"})

    assert captured.status_code == 200
    body = captured.json()
    assert body["captured"] is False
    assert "x-something-else" in body["seen_headers"]
    assert TOKEN_HEADER not in body["seen_headers"]


@pytest.mark.parametrize(
    "token",
    [
        "not-even-dotted",
        "!!!not-base64!!!.sig",
        f"{_b64url(b'this is not json')}.sig",
        f"{_b64url(json.dumps({'no': 'conversation id here'}).encode())}.sig",
    ],
)
def test_malformed_token_is_not_captured(client, token):
    captured = client.post("/push-token/capture", headers={TOKEN_HEADER: token})

    assert captured.status_code == 200
    assert captured.json()["captured"] is False


def test_unknown_conversation_is_404(client):
    assert client.get("/push-token/never-seen").status_code == 404


def test_the_latest_token_of_a_conversation_wins(client):
    client.post("/push-token/capture", headers={TOKEN_HEADER: make_token(tool_name="first")})
    client.post("/push-token/capture", headers={TOKEN_HEADER: make_token(tool_name="second")})

    assert client.get("/push-token/conv-1").json()["tool_name"] == "second"


def test_an_expired_token_is_not_served(client):
    client.post(
        "/push-token/capture",
        headers={TOKEN_HEADER: make_token(conversation_id="conv-old", ttl_seconds=-1)},
    )

    assert client.get("/push-token/conv-old").status_code == 404


def test_capturing_evicts_the_expired_entries_of_other_conversations():
    """Eviction is what keeps an in-memory store bounded, so it runs on write."""
    store = PushTokenStore()
    store.put(make_token(conversation_id="conv-stale", ttl_seconds=-1))

    store.put(make_token(conversation_id="conv-fresh"))

    assert store.get("conv-stale") is None
    assert store.get("conv-fresh") is not None


@pytest.mark.parametrize("path", ["/", "/health"])
def test_the_ingress_probes_answer(client, path):
    """The application gateway decides the backend is up from the root; without a 200 there the
    pod never goes into rotation, however well the capture endpoints work."""
    resp = client.get(path)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "push-token-capture"}
