import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from travel_agent.providers import ProviderError
from travel_agent.store import BudgetExceeded, SearchInProgress


def jobs_for(brief, request, max_options):
    if len(request.date_offsets) > max_options:
        raise ValueError(f"At most {max_options} date options are allowed per request")
    operations = request.operations
    if operations is None:
        operations = ["flights", "stays"] if brief.stay_location else ["flights"]
    if "stays" in operations and brief.stay_location is None:
        raise ValueError("Hotel search requires stay_location and explicit hotel dates")
    jobs = []
    for offset in request.date_offsets:
        if abs(offset) > brief.flexibility_days:
            raise ValueError("Date offset exceeds the trip's permitted flexibility")
        departure = brief.departure_date + timedelta(days=offset)
        returning = brief.return_date + timedelta(days=offset)
        if departure < datetime.now(UTC).date():
            raise ValueError("Date offset puts departure in the past")
        guests = [{"type": "adult"} for _ in range(brief.adults)]
        jobs.append(
            (
                offset,
                "flights",
                {
                    "slices": [
                        {
                            "origin": brief.origin,
                            "destination": brief.destination,
                            "departure_date": departure.isoformat(),
                        },
                        {
                            "origin": brief.destination,
                            "destination": brief.origin,
                            "departure_date": returning.isoformat(),
                        },
                    ],
                    "passengers": guests,
                    "cabin_class": "economy",
                    "max_connections": 1,
                },
            )
        )
        if brief.stay_location and "stays" in operations:
            jobs.append(
                (
                    offset,
                    "stays",
                    {
                        "rooms": brief.rooms,
                        "guests": guests,
                        "check_in_date": (brief.check_in_date + timedelta(days=offset)).isoformat(),
                        "check_out_date": (
                            brief.check_out_date + timedelta(days=offset)
                        ).isoformat(),
                        "location": {
                            "radius": brief.stay_location.radius_km,
                            "geographic_coordinates": {
                                "latitude": brief.stay_location.latitude,
                                "longitude": brief.stay_location.longitude,
                            },
                        },
                    },
                )
            )
    return [job for job in jobs if job[1] in operations]


class SearchService:
    def __init__(self, store, provider, settings):
        self.store, self.provider, self.settings = store, provider, settings
        self.semaphore = asyncio.Semaphore(settings.concurrency)

    async def run(self, trip_id, brief, request):
        jobs = jobs_for(brief, request, self.settings.date_limit)
        results = await asyncio.gather(
            *[
                self.execute(trip_id, offset, operation, payload)
                for offset, operation, payload in jobs
            ]
        )
        return {
            "trip_id": trip_id,
            "provider": self.settings.provider,
            "results": results,
            "usage": self.store.usage(trip_id, self.settings),
            "status": "discovery_only",
            "warning": "Search results are not reservations or a complete trip budget. "
            "Real supplier access and destination coverage still need verification.",
        }

    async def execute(self, trip_id, offset, operation, payload):
        key = hashlib.sha256(
            json.dumps(
                [trip_id, self.settings.provider, operation, payload],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        base = {"date_offset": offset, "operation": operation}
        async with self.semaphore:
            try:
                call_id, cached = self.store.claim(key, trip_id, self.settings, operation)
            except BudgetExceeded as exc:
                return {**base, "status": "budget_exhausted", "message": str(exc)}
            except SearchInProgress as exc:
                return {**base, "status": "in_progress", "message": str(exc)}
            if cached is not None:
                return {**base, "status": "cached", "result": cached}
            try:
                result = await self.provider.search(operation, payload)
                ttl = (
                    self.settings.cache_ttl
                    if (self.settings.provider == "mock" or self.settings.supplier_cache)
                    else 0
                )
                self.store.finish(key, call_id, result, ttl, "succeeded", result.get("request_id"))
                return {**base, "status": "succeeded", "result": result}
            except ProviderError as exc:
                self.store.finish(key, call_id, None, 0, "failed", exc.request_id)
                return {
                    **base,
                    "status": "provider_error",
                    "message": str(exc),
                    "request_id": exc.request_id,
                }
            except BaseException:
                self.store.finish(key, call_id, None, 0, "interrupted")
                raise
