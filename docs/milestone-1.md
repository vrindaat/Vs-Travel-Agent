# Milestone 1: prove supplier access and economics

Research checked November 7, 2026. Public documentation is evidence of published capabilities, not evidence that our account is approved.

## Launch brief — awaiting owner input

- Operating/company country: pending
- Personal-only pilot or commercial launch: pending
- Departure airport: pending
- First 1–3 destinations: pending
- Test travel dates and traveler count: pending
- Budget, currency, date flexibility: pending

Backend preparation proceeds without assuming these details. Route coverage cannot be assessed meaningfully until they are supplied.

## Evidence and decision log

| Supplier | Public evidence | Account status | Initial decision |
|---|---|---|---|
| Duffel Flights | Search API, eligible unpaid holds, public pricing, support/webhooks documentation | No token supplied; not tested against account | First sandbox candidate, conditional on country, content and servicing |
| Duffel Stays | Search/rates/quote/booking; separate access request | Access unverified | Test alongside Flights to reduce integration work |
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

Create a Duffel account, describe the personal pilot honestly, and request Stays access. Create a test API token. Add it to .env locally; never commit it. Production eligibility, business verification and payment onboarding are separate from sandbox signup.

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

Use the [single-search runbook](sandbox-runbook.md) to preview and execute each check separately. Local `.env` inspection on November 7, 2026 found mock mode and no configured test token. No account-backed sandbox or production search has been executed. Automated tests use synthetic results and HTTP transport fixtures only.

Record one case per route/date and accommodation query:

| Case | Requested market/dates | Provider request ID | Result / gaps | Verified by and date |
|---|---|---|---|---|
| Flight search | Pending | Pending | Not executed | Pending |
| Hotel search | Pending | Pending | Not executed | Pending |
| Authentication/access error | Pending | Pending | Fixture-tested only | Pending |
| Quote expiry/repricing | Pending | Pending | Not implemented | Pending |
| Hold/ticket/cancel/refund lifecycle | Pending | Pending | Not implemented | Pending |

Use sample or test traveler data. The implemented adapter performs search only. It cannot validate holds, ticketing, payments, refunds or end-to-end servicing. Those require a later controlled sandbox extension, an approved flow, and provider support.

## Acceptance criteria

- [ ] Operating country and target routes selected.
- [ ] Provider confirms account eligibility and flight/hotel permissions.
- [ ] Target flight and hotel searches succeed against our sandbox credentials, with recorded request IDs.
- [ ] Important inventory gaps and actual currency behavior recorded.
- [ ] Lifecycle capabilities, support ownership and payment requirements confirmed in writing.
- [ ] Pricing and data retention terms understood for the pilot.
- [x] Budget caps, timeout handling, caching and concurrent allowance reservations pass local tests (not booking reservations).
- [ ] Provider chosen with explicit reasons; milestone remains incomplete until the above evidence exists.

## Next engineering step

Once this gate passes, implement sourced destination research and itinerary/date optimization. Add model usage only to tasks that need language understanding. Budget model tokens, web search and mapping calls separately. Defer hosted workflow engines, Redis, vector databases and additional services until a measured workload justifies them; keep booking workflow boundaries explicit now.
