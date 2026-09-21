Written for: whoever picks this service up next — QA engineers running the parts suites, and whoever has to redeploy or debug it.

# Push Token Capture

A companion service for the QA parts suites. It exists for one reason: to receive the push token
agents-service mints, and hand it to a test.

## Why it exists

Pushing content into a conversation goes through advisor's
`POST /api/v1/conversations/{id}/external-parts`, which needs a `token`. That token is minted by
agents-service **per tool call** and handed to the tool it is invoking — push, not pull. There is
deliberately no endpoint to ask for one: possession of the token is the only proof the holder was
legitimately invoked for that conversation.

So a test gets one the way a real tool does. The canvas carries a REST tool pointing at
`/push-token/capture`; when the agent calls it, agents-service attaches the token as the
`x-domyn-push-token` header (every key of a tool call's `call_metadata` becomes a request header,
see `domyn_agents/tools/rest_function_tool.py`). This service pockets it, and the test reads it back.

The token is scoped to the conversation and to nothing else — agents-service validates the
signature, the expiry and the conversation id, never which tool it was issued to — so one captured
token authorizes whatever the test wants to push, for the hour it lives.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`/`POST` | `/push-token/capture` | Target of the canvas REST tool. Stores the token under the conversation it names. |
| `GET` | `/push-token/{conversation_id}` | The captured token, or `404` while the agent has not called the tool yet. |
| `GET` | `/` | Root probe — the application gateway reads this to decide the backend is up. |
| `GET` | `/health` | The same answer, at the path the ingress names as its health probe. |

`/push-token/capture` answers `200` whatever happens, including when no token arrived. It is
standing in for a tool, and a tool that fails is a turn that derails — the test would then be
debugging the agent instead of the capture. The truth is in the `captured` field, and when it is
`false` the response lists the header *names* it did see (never their values), which is what tells
you whether the platform sent the token at all.

## How it knows the conversation

The token is `base64url(payload_json).base64url(hmac)`. The payload half is plain, readable JSON —
only the signature needs the secret — so the service reads `conversation_id` straight out of it.
It therefore holds **no credentials of its own** and can never tell whether a token is genuine.
That is fine: a forged token stored here is simply rejected by agents-service when it is used.

## Constraints

- **Single replica.** The store is in memory and keyed by conversation. With two pods, the tool
  call that captures a token and the test call that reads it can land on different ones, and the
  read finds nothing.
- **Must be HTTPS.** Not for the network's sake — agents-service reaches cluster-internal hosts
  fine — but because console-service validates a REST connector's URL against `^https://` and
  refuses anything else with a 422. That is what this service is deployed for, rather than the
  endpoints simply living on `llm-check`.
- **Publicly reachable.** Anyone who knows a conversation id can read its token and push content
  into that conversation, for up to an hour. That is an accepted risk on QA; if it ever stops being
  acceptable, the read endpoint is the place to put a shared secret.

## Running locally

```bash
pip install fastapi "uvicorn[standard]" pydantic
uvicorn main:app --reload --port 8080
```

Tests need `pytest` and `httpx` (the latter comes with `fastapi[standard]`):

```bash
python -m pytest test -q
```

## Consumers

`testautomation-web`, via `$PUSH_TOKEN_SERVICE_URL` (`e2e-test/utils/ServiceUrls.ts` and
`e2e-test/page-objects/api/PushTokenService.api.ts`): the parts suites
`features/API/AgentsService/parts.feature` and `features/AgentsCanvas/Advisor/Parts.feature`.
