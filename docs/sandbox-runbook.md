# First account-backed supplier check

This procedure covers supplier searches. The owner's first authenticated sandbox flight search succeeded from regular PowerShell on November 10, 2026 Pacific time. Production access remains unverified. See the [current milestone evidence](milestone-1.md).

## Account setup

1. [Create a Duffel account](https://dashboard.duffel.com/join). Describe the actual country and personal/commercial intent; do not invent company details to complete onboarding.
2. Follow [Duffel's Flights setup guide](https://duffel.com/docs/guides/getting-started-with-flights): open **More > Developers > Access tokens** and create a **test** access token.
3. [Request Stays access](https://duffel.com/contact-us) separately, as required by the [Stays setup guide](https://duffel.com/docs/guides/getting-started-with-stays). Confirm personal-pilot eligibility with Duffel if the form's required business information does not fit your situation. The draft questions in [milestone-1.md](milestone-1.md) remain unsent.
4. Edit the existing ignored `.env` locally. Set `TRAVEL_PROVIDER=duffel_sandbox` and put the test token in `DUFFEL_ACCESS_TOKEN`. Leave `ALLOW_SUPPLIER_CACHE=false` until retention permission is confirmed. Never paste the token into chat or a shell command. Live tokens are rejected.
5. Restart the local API using the README command. Check `/v1/providers`: `selected` must be `duffel_sandbox`. Its access-verification flags deliberately remain false; a configured token does not prove account approval.

Account setup instructions were checked against these official guides on November 7, 2026. The Stays access link leads to a contact form; no form has been submitted by this project.

## Select the trip before searching

In `http://127.0.0.1:8000/docs`, authorize with your local bearer key if configured, then create the owner's selected brief through `POST /v1/trips`. Save the returned `trip_id` and reuse it across checks so the trip allowance accumulates. Do not use the example demo route as the launch test by default.

The brief needs origin/destination airport codes, future departure/return dates, adult count, budget amount and currency. Hotel checks additionally need owner-selected coordinates/radius, rooms, and explicit check-in/check-out dates. A flight check can use a brief with hotel details without searching hotels.

## Preview, then run one flight check

For the current pilot, continue with Chicago from regular PowerShell at the repository root.

```powershell
$comparison = Get-Content -LiteralPath data/pilot-flight-comparison.json -Raw | ConvertFrom-Json
$route = $comparison.routes | Where-Object destination -EQ 'ORD'
.\.bootstrap\Scripts\uv.exe --cache-dir data/uv-cache run --locked --no-sync --env-file .env python -m travel_agent.probe --trip-id $route.trip_id --operation flights --execute
```

Record the status, request ID, normalized offer count, and observed currencies. Use `MIA` for the Miami check after reviewing Chicago's result. If a request fails, keep the sanitized output and diagnose the error before spending another attempt. The command runs directly from PowerShell. For market price comparisons, use a source with live inventory. [Duffel test mode](https://duffel.com/docs/api/overview/test-mode/test-card-numbers)

For a different trip, use the generic preview and execution steps below.

Run from the repository root with the same `.env` and database as the API. Replace `YOUR_TRIP_ID` with the saved ID:

```powershell
.\.bootstrap\Scripts\uv.exe run --env-file .env python -m travel_agent.probe --trip-id YOUR_TRIP_ID --operation flights
```

The default is a preview: it shows the exact search payload and current allowances, makes no supplier requests, and consumes no allowance. Verify the provider, route, dates and travelers. To execute that single operation at date offset zero:

```powershell
.\.bootstrap\Scripts\uv.exe run --env-file .env python -m travel_agent.probe --trip-id YOUR_TRIP_ID --operation flights --execute
```

This uses the existing service and persistent counters. There is at most one outbound application attempt, no automatic retry, and no date expansion. A round-trip flight request contains two slices; one application attempt is not a verified supplier billing unit. Repeating supplier checks consumes another allowance when supplier caching is disabled. CLI execution is local and does not require the HTTP server to remain running.

The command also works in mock mode and clearly reports `synthetic_fixture`; that does not verify Duffel access. Exit codes: `0` for preview/completed search/cache, `1` for failed/blocked execution, `2` for invalid setup. A completed search with zero offers is not a coverage pass.

## Run a separate hotel check after access is confirmed

Preview with `--operation stays`. Only after the owner confirms Stays access, execute:

```powershell
.\.bootstrap\Scripts\uv.exe run --env-file .env python -m travel_agent.probe --trip-id YOUR_TRIP_ID --operation stays --execute --stays-access-confirmed
```

The flag is an owner acknowledgement for this command, not provider verification or a transaction approval record. A missing hotel location/dates is rejected before any supplier attempt.

The API offers the same operation selection through the search body:

```json
{"date_offsets": [0], "operations": ["flights"]}
```

Use `["stays"]` for only hotels. Omitting `operations` preserves the original behavior: flights and, if present in the brief, hotels. The example `demo.ps1` requires mock mode and refuses supplier mode.

## Record evidence without retaining inventory

The probe prints status, provider request ID, up to five normalized offers' count and observed currencies, the requested budget currency, and usage. It omits offer prices and hotel names. Currency conversion and total-trip budget evaluation remain unimplemented. Currency observations are limited to those normalized results.

`GET /v1/trips/{trip_id}/attempts` exposes existing durable attempt IDs, provider, operation, start time, status and provider request IDs. It uses the same local bearer protection as the trip/usage routes. It does not make supplier requests or persist supplier inventory. Request IDs from malformed supplier responses are retained when supplied in response headers. Missing IDs remain missing; do not invent them. A `reserved` attempt with no completion can indicate an interrupted process and still consumes allowance.

Copy the selected brief's dates/location, observed currencies, empty results or other gaps, and request IDs into the milestone worksheet. Keep any private trip notes under ignored `data/`. Do not store raw supplier responses, inventory or prices while retention permission remains unresolved. The CLI does not automatically save a report.

Record the evidence level explicitly:

- **Offline fixture tests:** exercise payloads, normalization, request limits and errors; no supplier account involved.
- **Account-backed sandbox search:** authenticates our test account and records the actual sandbox response. This remains test inventory and does not establish production coverage or servicing.
- **Production eligibility/coverage:** requires supplier confirmation of account permissions, target markets, commercial terms, support and lifecycle responsibilities. Production mode remains disabled.

Do not advance to destination research and itinerary optimization until the milestone acceptance gate is satisfied.
