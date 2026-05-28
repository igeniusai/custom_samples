# Domyn Platform — LangGraph Subagent Blueprint

A ready-to-run example of a deterministic LangGraph graph connected to the Domyn platform as a subagent. The graph implements a loan assessment pipeline: the platform orchestrator passes the user's input as a JSON object; the graph evaluates it through a set of deterministic rules and streams the decision back.

---

## What's included

```
blueprint/
├── loan_assessment_graph.py   # The graph — modify this to build your own logic
├── test_local.py              # Run the graph locally without a WebSocket connection
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # One-command local Docker run
├── requirements.txt           # Python dependencies (excl. domyn-agents wheel)
├── .env.example               # Required environment variables
└── wheels/                    # Place the domyn-agents .whl file here
```

---

## Prerequisites

- Python 3.11+ (for local/laptop runs)
- Docker (for containerised runs and VM deployment)
- The `domyn-agents` wheel file — place it in `wheels/`

---

## Step 0 — Prepare the wheel

Obtain the `domyn_agents-*.whl` file and place it inside the `wheels/` directory before running anything:

```bash
ls wheels/
```

---

## Step 1 — Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your values
```

| Variable | Description |
|---|---|
| `DOMYN_API_KEY` | API key from the Domyn platform |
| `CHANNEL_ID` | WebSocket channel ID assigned to this subagent |
| `SPACE_ID` | Your workspace ID on the platform |
| `CONFIGURATION_ID` | (Optional) Platform configuration ID; targets a specific configuration when registering invocation parameters |
| `PLATFORM_BASE_URL` | Platform base URL (e.g. `api.analy2.crystal.io`) |

---

## Running locally (laptop)

Install dependencies:

```bash
pip install wheels/domyn_agents-*.whl "langgraph>=0.2.0" "langchain-core>=0.3.0"
```

Test the graph without any platform connection:

```bash
python test_local.py
# or with a custom JSON input:
python test_local.py '{"salary": 80000, "loan_amount": 300000, "term_years": 30, "credit_score": 740, "monthly_debt": 300}'
```

Connect to the platform:

```bash
source .env
domyn expose loan_assessment_graph:graph \
    --framework   langgraph \
    --channel-id  $DOMYN_CHANNEL_ID \
    --space-id    $DOMYN_SPACE_ID \
    --base-url    $DOMYN_BASE_URL
```

`domyn expose` accepts a `module:symbol` argument pointing to a compiled LangGraph graph object. `loan_assessment_graph` is the Python module (i.e. `loan_assessment_graph.py`) and `graph` is the compiled graph instance exported from it. Any LangGraph graph can be served this way — change the argument to point to a different module or symbol as needed.

The process stays running and reconnects automatically on network drops.

---

## Running with Docker (laptop or VM)

Build the image:

```bash
docker build -t loan-assessment-blueprint .
```

Run (reads credentials from `.env`):

```bash
docker run --env-file .env loan-assessment-blueprint
```

Or with Docker Compose (one command):

```bash
docker compose up
```

---

## Deploying to a VM

1. Copy the blueprint directory to your VM:

```bash
scp -r blueprint/ user@your-vm:/opt/loan-assessment/
```

2. SSH into the VM and build:

```bash
ssh user@your-vm
cd /opt/loan-assessment
cp .env.example .env && nano .env   # fill in credentials
docker build -t loan-assessment-blueprint .
```

3. Run as a systemd service for automatic restart on reboot:

```ini
# /etc/systemd/system/loan-assessment.service
[Unit]
Description=Domyn Loan Assessment Subagent
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker run --rm --env-file /opt/loan-assessment/.env \
    --name loan-assessment loan-assessment-blueprint
ExecStop=/usr/bin/docker stop loan-assessment

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now loan-assessment
sudo journalctl -fu loan-assessment   # tail logs
```

---

## Graph overview

The graph is a linear deterministic pipeline — no LLM, no branching, no retries. Every valid invocation follows the same path from input to decision. Invalid input exits immediately with a structured error.

```
   Platform agent (user message — JSON object)
           │
           ▼
    ┌─────────────┐
    │ parse_input │  Parse the JSON object; validate required fields.
    └──────┬──────┘
           │
     ┌─────┴──────────────────────────────────────────────┐
     │ parse error?                                       │ ok
     ▼                                                    ▼
    END (structured error message            ┌──────────────────┐
     listing missing/invalid fields)         │ validate_income  │  salary < $20,000 → approved = False
                                             └────────┬─────────┘
                                                      │
                                                      ▼
                                             ┌───────────────┐
                                             │ calculate_dti │  monthly_payment (annuity) + monthly_debt
                                             │               │  ─────────────────────────────────────────
                                             └──────┬────────┘        monthly_income
                                                    │
                                                    ▼
                                             ┌─────────────┐
                                             │ assess_risk │  credit_score → risk tier
                                             │             │    ≥ 740  →  low
                                             │             │    ≥ 670  →  medium
                                             │             │    ≥ 580  →  high
                                             │             │    < 580  →  rejected
                                             └──────┬──────┘
                                                    │
                                                    ▼
                                             ┌───────────────┐
                                             │ make_decision │  Combine risk tier + DTI ratio:
                                             │               │    risk = rejected          → DENIED
                                             │               │    DTI  > 43%               → DENIED
                                             │               │    otherwise                → APPROVED
                                             └──────┬────────┘
                                                    │
                                                    ▼
                                             ┌───────────────┐
                                             │ format_result │  Render human-readable summary string
                                             └──────┬────────┘
                                                    │
                                                    ▼
                                        WebSocket relay → platform agent
```

**State object** — all nodes read from and write to a single `LoanState` dict that flows through the pipeline:

| Field | Type | Set by |
|---|---|---|
| `raw_input` | str | input_mapper |
| `salary`, `loan_amount`, `term_years`, `credit_score`, `monthly_debt` | float / int | `parse_input` |
| `parse_error` | bool | `parse_input` |
| `dti_ratio` | float | `calculate_dti` |
| `risk_level` | str | `assess_risk` |
| `approved` | bool \| None | `validate_income`, `make_decision` |
| `reason` | str | `validate_income`, `make_decision` |
| `result` | str | `parse_input` (on error), `format_result` |

---

## Customising the graph

All business logic lives in `loan_assessment_graph.py`. The graph runs these nodes in order:

| Node | What it does |
|---|---|
| `parse_input` | Parses the JSON input; exits with a structured error if fields are missing or malformed |
| `validate_income` | Rejects if annual salary < $20,000 |
| `calculate_dti` | Computes debt-to-income ratio using an annuity formula |
| `assess_risk` | Maps credit score to a risk tier (low / medium / high / rejected) |
| `make_decision` | Combines DTI and risk tier into an approval decision |
| `format_result` | Renders a human-readable summary |

**Common customisations:**
- Change income threshold → edit `validate_income`
- Change DTI limit (currently 43%) → edit `make_decision`
- Change credit score bands → edit `assess_risk`
- Add a new input field (e.g. `employment_type`) → add it to `LoanState`, `_REQUIRED_FIELDS`, and parse it in `parse_input`

After changes, re-run `python test_local.py` to verify before connecting to the platform.

---

## Input format

The platform orchestrator sends the user message as a plain string under the `task` key. The graph expects this string to be a JSON object (or contain one) with the following fields:

```json
{
  "salary": 70000,
  "loan_amount": 250000,
  "term_years": 30,
  "credit_score": 720,
  "monthly_debt": 400
}
```

| Field | Type | Unit | Description |
|---|---|---|---|
| `salary` | number | Annual USD | Applicant's gross annual salary |
| `loan_amount` | number | USD | Total loan amount requested |
| `term_years` | integer | Years | Loan repayment term |
| `credit_score` | integer | 300–850 | Applicant's credit score |
| `monthly_debt` | number | Monthly USD | Existing monthly debt obligations |

All fields are required. If any are missing or cannot be coerced to the expected numeric type, the graph returns a structured error message that lists the missing/invalid fields and shows a valid example — the calling agent can read this and retry.

The parser is lenient: if the input string contains surrounding prose (e.g. the agent wraps the JSON in a sentence), the outermost `{...}` block is extracted automatically.

---

## Testing end-to-end

Once the agent is connected and the process is running, trigger it from the Domyn platform canvas by sending a message like:

```json
{"salary": 70000, "loan_amount": 250000, "term_years": 30, "credit_score": 720, "monthly_debt": 400}
```

Expected response:

```
Loan Assessment: APPROVED
  Applicant salary:    $70,000/yr
  Loan requested:      $250,000 over 30 years
  Credit score:        720 (MEDIUM risk)
  Debt-to-income:      30.5%
  Decision reason:     Good credit profile; standard terms apply.
```
