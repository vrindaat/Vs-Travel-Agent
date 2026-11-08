# VS Travel Agent

Milestone one: supplier discovery and a small, cost-bounded backend. This is a local, single-user development foundation. It does not yet research destinations, optimize a full itinerary, reserve anything, or accept payments.

## Run locally

Python 3.12 and uv are used; dependencies are pinned in uv.lock after setup.
If uv is already installed:

```powershell
uv sync --locked
Copy-Item -LiteralPath .env.example -Destination .env
uv run --env-file .env uvicorn travel_agent.api:create_app --factory --host 127.0.0.1 --port 8000
```

If only the older system Python is installed, bootstrap uv inside this project:

```powershell
py -m venv .bootstrap
.bootstrap\Scripts\python.exe -m pip install uv
.bootstrap\Scripts\uv.exe sync --python 3.12
Copy-Item -LiteralPath .env.example -Destination .env
.bootstrap\Scripts\uv.exe run --env-file .env uvicorn travel_agent.api:create_app --factory --host 127.0.0.1 --port 8000
```

Use the same local uv executable for subsequent commands. Python 3.12 can be downloaded by uv automatically. This leaves the system Python unchanged.

Open http://127.0.0.1:8000/docs for the interactive API. In a second PowerShell terminal, run:

```powershell
.\scripts\demo.ps1
```

The demo route LHR–LIS is an example, not a recommendation or the selected launch market. Mock mode returns conspicuously labeled synthetic fixtures, never current prices or availability.

## Check the code

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## First supplier check

1. Read [the milestone checklist](docs/milestone-1.md).
2. Create a [Duffel account](https://dashboard.duffel.com/join) and request Stays access.
3. Create a test token. Store it only in the ignored .env file, not chat, source code, screenshots, or GitHub.
4. Set TRAVEL_PROVIDER=duffel_sandbox and DUFFEL_ACCESS_TOKEN=your test token, then restart.
5. Try one flight search. Request a hotel search only after Stays access is available.
6. Record provider request IDs, coverage gaps, and support answers in the checklist.

Use the [sandbox runbook](docs/sandbox-runbook.md) for account setup and the preview-first, single-search command. The probe reuses an existing trip and its persistent allowance; it searches only flights or only hotels, at date offset zero. `demo.ps1` now requires mock mode.

This adapter accepts only duffel_test_ credentials and implements only flight/hotel searches. It does not verify production account approval. Mock and transport-fixture tests do not establish live supplier access.

## API

| Endpoint | Purpose |
|---|---|
| GET /health | Local health and transaction-disabled flags |
| GET /v1/providers | Selected provider and deliberately unverified access flags |
| POST /v1/trips | Validate and save a trip brief |
| GET /v1/trips/{id} | Read the brief |
| POST /v1/trips/{id}/search | Compare explicitly requested date offsets |
| GET /v1/trips/{id}/usage | Read durable call counters |
| GET /v1/trips/{id}/attempts | Read saved attempt metadata and provider request IDs |

Hotel location coordinates and check-in/check-out dates are explicit. The backend never assumes an overnight flight lands on its departure date. Shifting dates keeps trip length and hotel offsets fixed; varying trip duration is a later planner feature. Adults only in this first supplier probe.

Search results retain original currencies. No currency conversion, all-in budget optimization, or booking recommendation is performed.

For a flight-only check, send `{"date_offsets":[0],"operations":["flights"]}` to the search endpoint. Use `["stays"]` for hotels only; hotel details must exist in the brief. Omitting `operations` preserves the original combined behavior.

## Keeping costs low

- No AI calls or model keys are needed for supplier discovery.
- Default maximum: three date options per request, twelve supplier attempts per trip, sixty application-wide per UTC day.
- Failed requests consume allowance; upstream searches are not automatically retried.
- SQLite transactionally reserves allowance before network calls, including concurrent requests; counters survive application restarts.
- Two concurrent supplier requests per process, with bounded total request time.
- Repeated mock searches reuse a short-lived cache. Supplier caching is off until retention permission is confirmed; then expiry never exceeds the supplier expiry.
- Response normalization limits returned offers to five, avoiding unnecessary future model context.
- In-flight duplicate searches are blocked with a short lease.

These are application request limits, not verified supplier billing units or a guaranteed dollar ceiling. Supplier internal fan-out and fee definitions must be confirmed. The global daily cap prevents new trip IDs from bypassing the trip cap.

## Before production

Add real user authentication and ownership checks, request/body and infrastructure rate limits, encrypted backups and retention controls, a PostgreSQL migration, durable workflows for booking, approval records, idempotency/reconciliation, payment integration, and an operational servicing agreement. Add provider contract tests using a real sandbox account.

TRAVEL_API_KEY is an optional shared local key, not multi-user authorization. Bind only to 127.0.0.1 for this milestone. Each process has its own concurrency semaphore; keep one worker for the pilot. SQLite allowance reservations are shared across processes on the same host, not across machines. The single-user API stores no passport or card data.

Keep the host and gateway isolated before exposing the API: application call caps do not prevent denial of service or constrain bandwidth/memory for an unbounded supplier response. Supplier/provider API bodies and secrets are not logged.
