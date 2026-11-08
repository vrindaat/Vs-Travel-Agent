"""Preview or execute one discovery search using the existing trip and durable limits."""

import argparse
import asyncio
import json

from pydantic import ValidationError

from travel_agent.config import Settings
from travel_agent.models import SearchRequest, TripBrief
from travel_agent.providers import DuffelSandboxProvider, MockProvider
from travel_agent.service import SearchService, jobs_for
from travel_agent.store import Store


class ProbeError(ValueError):
    pass


async def probe(settings, trip_id, operation, *, execute=False, stays_access_confirmed=False):
    if not settings.database.is_file():
        raise ProbeError("Database not found; create a trip through the local API first")
    store = Store(settings.database)
    data = store.get_trip(trip_id)
    if data is None:
        raise ProbeError("Trip not found; use an existing trip ID from the local API")
    try:
        brief = TripBrief.model_validate(data, context={"stored_brief": True})
    except ValidationError:
        raise ProbeError("Stored trip brief is invalid") from None
    request = SearchRequest(operations=[operation], date_offsets=[0])
    jobs = jobs_for(brief, request, settings.date_limit)
    report = {
        "mode": "execute" if execute else "preview",
        "trip_id": trip_id,
        "provider": settings.provider,
        "operation": operation,
        "search_payload": jobs[0][2],
        "max_outbound_attempts": 1,
        "automatic_retries": 0,
        "usage_before": store.usage(trip_id, settings),
        "production_access_verified": False,
        "note": "Application attempts are not supplier billing units or a dollar ceiling. "
        "Sandbox success does not establish production inventory or servicing.",
    }
    if not execute:
        return report
    if (
        settings.provider == "duffel_sandbox"
        and operation == "stays"
        and not stays_access_confirmed
    ):
        raise ProbeError("Confirm Stays access first, then pass --stays-access-confirmed")
    provider = MockProvider() if settings.provider == "mock" else DuffelSandboxProvider(settings)
    try:
        response = await SearchService(store, provider, settings).run(trip_id, brief, request)
    finally:
        await provider.close()
    row = response["results"][0]
    result = row.get("result", {})
    offers = result.get("offers", [])
    report.update(
        status=row["status"],
        source=result.get("source"),
        request_id=result.get("request_id", row.get("request_id")),
        message=row.get("message"),
        normalized_offer_count=len(offers),
        currencies_observed=sorted({offer["currency"] for offer in offers}),
        requested_budget_currency=brief.budget_currency,
        usage_after=response["usage"],
        evidence_note="Count and currencies cover at most five normalized offers. "
        "An empty result does not establish route coverage. No currency conversion performed. "
        "Only attempt metadata and request IDs are persisted when supplier caching is off.",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trip-id", required=True)
    parser.add_argument("--operation", choices=("flights", "stays"), default="flights")
    parser.add_argument(
        "--execute", action="store_true", help="Execute at most one supplier attempt"
    )
    parser.add_argument(
        "--stays-access-confirmed", action="store_true", help="Owner confirms sandbox Stays access"
    )
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(
            probe(
                Settings.from_env(),
                args.trip_id,
                args.operation,
                execute=args.execute,
                stays_access_confirmed=args.stays_access_confirmed,
            )
        )
    except ProbeError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    except (ValueError, OSError):
        # Do not print exception input: configuration and stored records may contain secrets.
        print(
            json.dumps({"error": "Probe setup failed; check settings, trip ID, dates and access"})
        )
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") in (None, "succeeded", "cached") else 1


if __name__ == "__main__":
    raise SystemExit(main())
