import base64
import binascii
import json
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# The header agents-service uses to hand a freshly minted push token to a REST tool it is
# invoking (agents_service/hooks/external_part.py, TOOL_TOKEN_KEY). Same `x-domyn-*`
# convention as the other headers the platform passes around.
TOKEN_HEADER = "x-domyn-push-token"


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def read_token_payload(token: str) -> Optional[dict]:
    """Reads the claims out of a push token without verifying it.

    The token is `base64url(payload_json).base64url(hmac)`, and only agents-service holds the
    secret - so this service can read the payload but can never say whether it is genuine.
    That is fine for what it does: it hands the token straight back to the test, and advisor
    (really agents-service, behind it) is the one that validates it for real. A forged token
    stored here would simply be rejected there.

    Returns None for anything that is not a token carrying a conversation id.
    """
    try:
        payload_b64, _signature_b64 = token.split(".", 1)
    except ValueError:
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict) or not payload.get("conversation_id"):
        return None

    return payload


class PushTokenStore:
    """Remembers the last push token seen for each conversation.

    In memory on purpose: the tokens live an hour at most and matter only for the scenario
    that is running. It does mean the service must run as a single replica - with two pods
    the tool call that captures a token and the test call that reads it can land on
    different ones, and the read finds nothing.
    """

    def __init__(self):
        self._by_conversation: Dict[str, dict] = {}

    def put(self, token: str) -> Optional[dict]:
        """Stores a token under the conversation it was minted for. Returns its payload,
        or None when the token cannot be read - a caller that gets None captured nothing."""
        payload = read_token_payload(token)
        if payload is None:
            return None

        self._evict_expired()
        self._by_conversation[payload["conversation_id"]] = {
            "token": token,
            "tool_name": payload.get("tool_name"),
            "exp": payload.get("exp"),
            "message_id": payload.get("message_id"),
            "captured_at": int(time.time()),
        }
        return payload

    def get(self, conversation_id: str) -> Optional[dict]:
        entry = self._by_conversation.get(conversation_id)
        if entry is None:
            return None
        if self._is_expired(entry):
            # Serving it would only push the failure downstream, where agents-service
            # answers an opaque 404 that says nothing about why.
            del self._by_conversation[conversation_id]
            return None
        return entry

    def clear(self):
        self._by_conversation.clear()

    def _evict_expired(self):
        """Keeps the store bounded. Runs on write: nothing else here happens often enough
        to be worth a background task."""
        expired = [
            conversation_id
            for conversation_id, entry in self._by_conversation.items()
            if self._is_expired(entry)
        ]
        for conversation_id in expired:
            del self._by_conversation[conversation_id]

    @staticmethod
    def _is_expired(entry: dict) -> bool:
        exp = entry.get("exp")
        if exp is None:
            return False
        return exp <= int(time.time())
