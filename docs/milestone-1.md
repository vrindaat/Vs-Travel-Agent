# Milestone 1: prove supplier access and economics

Research checked November 7, 2026. Public documentation is evidence of published capabilities, not evidence that our account is approved.

## Launch brief — local pilot intake recorded

The owner has supplied operating country, personal-only pilot intent, departure airport, three destination names, dates, traveler count, budget and date flexibility. Private trip details are recorded in ignored `data/pilot-intake.json`, outside Git.

The owner confirms that the destinations are alternatives, all travelers are adults, and there is no fixed hotel room preference. Room count remains open for a future cost comparison using supplier-permitted occupancy; the flight-only brief's default room count is not a selected hotel arrangement. The date year is inferred as 2026. No hotel search is authorized or attempted before Stays access is confirmed.

## Evidence and decision log

| Supplier | Public evidence | Account status | Initial decision |
|---|---|---|---|
| Duffel Flights | Search API, eligible unpaid holds, public pricing, support/webhooks documentation | Authenticated sandbox search succeeded from the owner's terminal | First sandbox candidate, conditional on country, content and servicing |
| Duffel Stays | Search/rates/quote/booking; separate access request | Owner has not requested access; no hotel calls made | Request access before a separate bounded hotel test |
| Booking.com Demand | Managed affiliate prerequisites and order creation | No partner agreement confirmed | Alternative, not a launch dependency |
| Expedia Rapid | Hotel hold/resume documented | Access unverified | Alternative if inventory or servicing is better |
| Viator | Basic affiliate redirects; Full + Booking requires approval/certification | Access unverified | Assess after core flight/hotel supplier check |

Sources:
- [Duffel pricing](https://duffel.com/pricing)
- [Flight offer request schema](https://duffel.com/docs/api/offer-requests/create-offer-request)
- [Stays search schema](https://duffel.com/docs/api/v2/search)
- [Stays onboarding](https://duffel.com/docs/guides/getting-started-with-stays)
- [Holding flights](https://duffel.com/docs/guides/holding-orders-and-paying-later)
- [Handling uncertain booking responses](https://duffel.com/docs/api/overview/response-handling)
- [Booking.com prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites)
- [Expedia hotel holds](https://developers.expediagroup.com/rapid/lodging/booking/hold-resume)
- [Viator access levels](https://partnerresources.viator.com/travel-commerce/levels-of-access/)

## What the owner does first

The owner reports a Duffel account and has saved a test token in the ignored `.env`. Local configuration now selects `duffel_sandbox`, with supplier caching disabled. Token-prefix and configuration checks do not verify authentication or account permissions.

Request Stays access, describing the personal pilot honestly. An unsent draft is available locally in ignored `data/stays-access-request-draft.txt`. Production eligibility, business verification and payment onboarding are separate from sandbox signup.

Do not submit speculative company facts or accept a commercial agreement before reviewing its obligations.

## Questions to resolve with the provider

Draft only — nothing has been sent.

- Can a personal pilot use the sandbox, and what entity and country requirements apply to live access?
- Are the target airlines/routes and hotel destinations covered? What content and loyalty gaps exist?
- Who is responsible for ticketing, changes, cancellations, refunds and out-of-hours emergencies?
- What is automated through the API, what requires support, and what are the response expectations?
- Which offers support holds? What are seat, room, price-guarantee and payment deadlines?
- What are payment authorization, settlement, prefunding, FX, chargeback and refund requirements?
- How are search requests, date expansion, ancillary calls, failed requests and internal supplier fan-out billed?
- How do search-to-book charges work during a low-conversion pilot or a month with zero bookings?
- What retention, caching, AI processing and display permissions apply to inventory and prices?
- What certification, contractual support, geographic restrictions and production limits apply?

## Public cost reference — not a negotiated quote

Duffel's USD public page currently lists $3 per confirmed flight order, 1% Managed Content fee, $2 per paid ancillary, and $0.005 per excess search above its stated 1500:1 search-to-order ratio; FX fees are also listed. Confirm which fees combine and how they apply to this account.

For illustration only, a $1,000 Managed Content order would have $3 + $10 = $13 in those two fee categories, before any ancillary, payment, FX, excess-search or support costs. A payment-free sandbox search is not a production unit-economics test.

The backend meters outbound HTTP attempts, not this commercial definition of billable searches. No supplier caching permission or monthly dollar guarantee is assumed.

## Sandbox validation worksheet

Use the [single-search runbook](sandbox-runbook.md) to preview and execute each check separately. The November 7, 2026 flight attempt failed before a supplier response. On November 10, 2026 Pacific time, the owner ran the same flight check from regular PowerShell. The local attempt log records a successful sandbox response and a Duffel request ID. This verifies sandbox flight access for the account. The owner's command output, matched to that request ID, confirms five normalized offers in USD, matching the brief's currency. The adapter returns at most five normalized offers, so this count represents the returned selection.

The private brief, trip ID, and attempt evidence are in ignored `data/pilot-flight-probe.json` and `data/pilot-flight-evidence.json`. The evidence preserves both attempts and the successful request ID. Production eligibility, inventory, and pricing remain unverified.

The workspace connectivity check was denied before sending an API request. The three route briefs were validated offline and saved in ignored `data/pilot-flight-comparison.json`. Run the remaining checks individually from regular PowerShell.

Record one case per route/date and accommodation query:

| Case | Requested market/dates | Provider request ID | Result / gaps | Verified by and date |
|---|---|---|---|---|
| Flight search | Private local brief, round trip at offset zero | Recorded privately | Sandbox access verified. Five normalized offers in USD, matching the brief currency. | Local attempt log and owner command output, November 10, 2026 Pacific time |
| Hotel search | Flexible room count; supplier-permitted occupancy and approved access required | None | Not executed; access not requested | Owner status, November 7, 2026 |
| Authentication/access error | Pending | Pending | Fixture-tested only | Pending |
| Quote expiry/repricing | Pending | Pending | Not implemented | Pending |
| Hold/ticket/cancel/refund lifecycle | Pending | Pending | Not implemented | Pending |

Use sample or test traveler data. The implemented adapter performs search only. It cannot validate holds, ticketing, payments, refunds or end-to-end servicing. Those require a later controlled sandbox extension, an approved flow, and provider support.

## Acceptance criteria

- [x] Operating country and target destination alternatives selected; private details recorded locally.
- [x] First authenticated sandbox flight search succeeded with a recorded request ID.
- [ ] Provider confirms account eligibility and flight/hotel permissions.
- [ ] Target flight and hotel searches succeed against our sandbox credentials, with recorded request IDs.
- [ ] Important inventory gaps and actual currency behavior recorded.
- [ ] Lifecycle capabilities, support ownership and payment requirements confirmed in writing.
- [ ] Pricing and data retention terms understood for the pilot.
- [x] Budget caps, timeout handling, caching and concurrent allowance reservations pass local tests (not booking reservations).
- [ ] Provider chosen with explicit reasons; milestone remains incomplete until the above evidence exists.

## Next engineering step

Once this gate passes, implement sourced destination research and itinerary/date optimization. Add model usage only to tasks that need language understanding. Budget model tokens, web search and mapping calls separately. Defer hosted workflow engines, Redis, vector databases and additional services until a measured workload justifies them; keep booking workflow boundaries explicit now.
