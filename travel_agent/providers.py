import asyncio
import time
from datetime import datetime
from decimal import Decimal

import httpx


class ProviderError(Exception):
    def __init__(self, message, request_id=None):
        super().__init__(message)
        self.request_id = request_id


class MockProvider:
    async def search(self, operation, payload):
        await asyncio.sleep(0)
        return {
            "source": "synthetic_fixture",
            "operation": operation,
            "offers": [
                {
                    "id": f"mock_{operation}",
                    "amount": "420.00" if operation == "flights" else "650.00",
                    "currency": "USD",
                    "description": "Synthetic fixture; no real availability or reservation",
                }
            ],
            "valid_until": time.time() + 120,
            "bookable": False,
            "requires_fresh_quote": True,
        }

    async def close(self):
        pass


class DuffelSandboxProvider:
    # Deliberately no generic URL, reservation, hold, payment or cancellation capability.
    SEARCH_PATHS = {"flights": "/air/offer_requests", "stays": "/stays/search"}

    def __init__(self, settings, transport=None):
        if not settings.token.startswith("duffel_test_"):
            raise ValueError("Only Duffel test credentials are accepted")
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url="https://api.duffel.com",
            headers={
                "Authorization": f"Bearer {settings.token}",
                "Duffel-Version": "v2",
                "Accept": "application/json",
            },
            timeout=settings.timeout,
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=settings.concurrency, max_keepalive_connections=settings.concurrency
            ),
            transport=transport,
        )

    async def search(self, operation, payload):
        if operation not in self.SEARCH_PATHS:
            raise ProviderError("Operation is not an allowed supplier search")
        params = None
        if operation == "flights":
            params = {
                "return_offers": "true",
                "supplier_timeout": max(2000, (self.settings.timeout - 2) * 1000),
            }
        request_id = None
        try:
            async with asyncio.timeout(self.settings.timeout):
                response = await self.client.post(
                    self.SEARCH_PATHS[operation], json={"data": payload}, params=params
                )
            request_id = response.headers.get("x-request-id")
            if response.status_code >= 300:
                raise ProviderError(f"Supplier returned HTTP {response.status_code}", request_id)
            body = response.json()
            data = body["data"]
            if data.get("live_mode") is True or (
                operation == "flights" and data.get("live_mode") is not False
            ):
                raise ProviderError("Supplier response did not confirm test mode", request_id)
            result = self.normalize(operation, body["data"])
            result["request_id"] = request_id
            return result
        except ProviderError:
            raise
        except (TimeoutError, httpx.HTTPError):
            raise ProviderError("Supplier search timed out or could not be reached") from None
        except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
            raise ProviderError(
                "Supplier returned an unexpected search response", request_id
            ) from None

    def normalize(self, operation, data):
        offers = []
        valid_until = time.time() + self.settings.cache_ttl
        rows = data.get("offers", []) if operation == "flights" else data.get("results", [])
        for row in rows:
            if row.get("expires_at"):
                expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
                if expires.timestamp() <= time.time():
                    continue
                valid_until = min(valid_until, expires.timestamp())
            if operation == "flights":
                segments = [
                    segment
                    for part in row.get("slices", [])
                    for segment in part.get("segments", [])
                ]
                item = {
                    "id": row["id"],
                    "amount": row["total_amount"],
                    "currency": row["total_currency"],
                    "expires_at": row.get("expires_at"),
                    "operating_carriers": sorted(
                        {s["operating_carrier"]["name"] for s in segments}
                    ),
                    "segments": [
                        {
                            "origin": s["origin"]["iata_code"],
                            "destination": s["destination"]["iata_code"],
                            "departing_at": s["departing_at"],
                            "arriving_at": s["arriving_at"],
                        }
                        for s in segments
                    ],
                }
            else:
                item = {
                    "id": row["id"],
                    "amount": row["cheapest_rate_total_amount"],
                    "currency": row["cheapest_rate_currency"],
                    "accommodation": row.get("accommodation", {}).get("name"),
                }
            amount = Decimal(item["amount"])
            if not amount.is_finite() or amount < 0:
                raise ValueError("Invalid amount")
            offers.append(item)
        # Do not rank different currencies as interchangeable amounts.
        offers.sort(key=lambda x: (x["currency"], Decimal(x["amount"])))
        return {
            "source": "supplier_sandbox",
            "operation": operation,
            "offers": offers[:5],
            "valid_until": valid_until,
            "bookable": False,
            "requires_fresh_quote": True,
        }

    async def close(self):
        await self.client.aclose()
