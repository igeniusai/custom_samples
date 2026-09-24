# watcher_example

Minimal FastAPI blueprint that receives Domyn hook events, logs them, and
acknowledges them. Useful as a starting point for a hook that only needs to
observe traffic (e.g. auditing, metrics) without modifying or blocking it.

It also exposes two custom UIs: a per-message view listing the raw events
received for that turn, and a space-level settings view to toggle which
checks (PII, Toxicity, Prompt Injection) run against received events.

## Endpoints

| Method | Path                                       | Description                                                |
| ------ | ------------------------------------------ | ----------------------------------------------------------- |
| POST   | `/watch_event`                             | Logs the incoming event, records it, returns `HookResult`. Must return HookResult immediately with success=True to avoid blocking the execution flow. Execute any operation in the background  |
| GET    | `/watch_event/event-history`               | Custom UI iframe listing received events for a message      |
| GET    | `/watch_event/event-history/data`          | Event history JSON, optionally filtered by `message_id` or `conversation_id` |
| DELETE | `/watch_event/event-history/data`          | Clear the history (all turns, or just `message_id`)         |
| GET    | `/watch_event/settings`                    | Custom UI iframe to toggle the checks run on received events |
| POST   | `/watch_event/settings`                    | Update which checks are enabled                              |
| GET    | `/watch_event/settings/data`               | Current check configuration as JSON                          |
| GET    | `/watch_event/.well-known/domyn-custom-ui` | Discovery metadata for both custom UI views                 |
| POST   | `/input_hook`                              | Pass-through "before the answer" hook                        |
| POST   | `/output_hook`                             | Pass-through "after the answer" hook                         |
| GET    | `/hooks/invocations`                       | Pass-through hook calls, optionally filtered by `turn_id`    |
| DELETE | `/hooks/invocations`                       | Clear the recorded pass-through hook calls                   |
| GET    | `/health`                                  | Liveness check                                               |

### Request (`HookRequest`)

```json
{
  "current_event": {},
  "interaction_history": [],
  "interaction_context": {}
}
```

All fields are optional.

### Response (`HookResult`)

```json
{
  "success": true,
  "break_execution": false,
  "modified_event": null
}
```

`modified_event` is optional and only meaningful for updater-style hooks:
set it to a dict to have that event replace `current_event` in the
execution flow, or leave it `null` to pass the event through unchanged.
This example hook only observes traffic and always returns the default
`HookResult()`, so `modified_event` is never populated here.

## Running locally

```bash
make install
make dev
```

The app listens on `http://localhost:8089`.

## Running with Docker

```bash
make build
make run
```

This starts the container and maps port `8089` to `localhost:8089`.

```bash
curl -X POST http://localhost:8089/watch_event \
  -H 'Content-Type: application/json' \
  -d '{"current_event": {"foo": "bar", "turn_id": "t1"}}'
```

Tail logs with `make logs`, stop with `make stop`.

---

## Event history custom UI

Every event whose `current_event` includes a `turn_id` is kept in memory,
grouped by that `turn_id`. Events without a `turn_id` are still
acknowledged but are not recorded (this is logged).

`GET /watch_event/event-history` renders an iframe view — embedded in the
Domyn canvas next to each message — that polls
`/watch_event/event-history/data?message_id=<turn_id>` and displays the raw
JSON of every event received for that turn, most recent last. Opened at the
conversation level (no `message_id`, only `conversation_id`) it shows the turns
of that conversation; with neither it shows an empty state and never fetches the
unscoped history, which holds every turn of every caller. The view polls every
5s, only while it is visible, and leaves the DOM untouched when nothing changed;
responses are gzip-compressed.

History is runtime-only: it is not persisted to disk and is cleared on
restart. It keeps the most recent `MAX_HISTORY_TURNS` turns (200) and evicts
the oldest beyond that, so it stays bounded without anyone having to empty
it. That matters because the store is shared by every caller: automated
tests read it through the `message_id` of their own turn and must NOT wipe
it, or they wipe the turns a concurrently running test is still collecting.
`DELETE /watch_event/event-history/data` drops it without a restart — the
whole history, or a single turn with `?message_id=<turn_id>` — for manual
use. It is idempotent and reports how many turns it dropped.

## Check settings custom UI

`GET /watch_event/settings` renders a space-level iframe view with a
checkbox per check — **PII**, **Toxicity**, **Prompt Injection** — all
disabled by default. Saving posts the 3 booleans to
`POST /watch_event/settings`, which updates the in-memory check
configuration (not persisted to disk; resets to all-disabled on restart).

`GET /watch_event/settings/data` returns the same configuration as JSON,
which is how a caller can assert what was saved without scraping the iframe.

Detection is deliberately simple but real, not mocked: each check matches a
pattern against the text of `user_input` and `response` events only (every
other event type yields no text, hence no checks) — PII looks for an email
address, Toxicity for the word "stupid", Prompt Injection for the phrase
"ignore system instructions" — and reports `"passed"` or `"failed"`. Each one
sleeps `CHECK_DELAY_SECONDS` (10s) to emulate a heavier scanning service;
enabled checks run concurrently in a background task, so the result lands on
the entry ~10s after the event was acknowledged.

When `/watch_event` records an event, it runs whichever checks are currently
enabled and stores the result alongside that event. The event-history UI then
shows a badge per check that was actually run for that event (e.g.
`PII: passed`), so toggling a check only affects events received afterward —
it does not retroactively apply to history already recorded.

---

## Pass-through before/after hooks

`POST /input_hook` and `POST /output_hook` are ordinary hook endpoints that observe and
acknowledge: they always return the default `HookResult()`, so they never modify or
block, and a conversation behaves exactly as it would with no hook at all. They exist so
one canvas can carry a **watcher hook and ordinary input/output hooks at the same time**
without pulling in a second service.

Each call is recorded in memory (hook name, `turn_id`, `event_type`, `author`) and
exposed by `GET /hooks/invocations`, so a caller can assert that a hook really ran on a
given turn. `DELETE /hooks/invocations` clears the log; both are runtime-only, like the
event history.

This log is deliberately **separate from the event history**: nothing here touches
`/watch_event/event-history/data`, so asserting on recorded agent events is not polluted
by these invocations — and, more importantly, "was the input hook invoked?" stays
answerable independently of whether the watcher received the corresponding
`hook_start`/`hook_end` events.

That distinction matters, because measured on QA it does **not**: the pass-through hooks
run (their invocations are recorded with the turn's `turn_id`) while the watcher receives
no `hook_*` event whatsoever for the same turn, even though a watcher hook subscribes to
`hook_start`, `hook_update`, `hook_end` and `hook_error`. Plausibly deliberate —
delivering hook events to a hook would feed a watcher its own invocations — but worth
confirming upstream.
