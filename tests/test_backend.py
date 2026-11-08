import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from travel_agent.api import create_app
from travel_agent.config import Settings
from travel_agent.models import SearchRequest, TripBrief
from travel_agent.providers import DuffelSandboxProvider, MockProvider, ProviderError
from travel_agent.service import SearchService, jobs_for
from travel_agent.store import BudgetExceeded, SearchInProgress, Store


def brief_data(**overrides):
    departure = datetime.now(UTC).date() + timedelta(days=30)
    result = {
        "origin": "LHR",
        "destination": "LIS",
        "departure_date": str(departure),
        "return_date": str(departure + timedelta(days=7)),
        "adults": 2,
        "budget_amount": "4000.00",
        "flexibility_days": 3,
        "stay_location": {"latitude": 38.7223, "longitude": -9.1393},
        "check_in_date": str(departure),
        "check_out_date": str(departure + timedelta(days=7)),
    }
    return result | overrides


def settings_for(tmp_path, **overrides):
    return Settings(database=tmp_path / "travel.sqlite3", **overrides)


def new_trip(client, **overrides):
    response = client.post("/v1/trips", json=brief_data(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["trip_id"]


def test_mock_search_cache_and_restart_persistence(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        trip = new_trip(client)
        url = f"/v1/trips/{trip}/search"
        first = client.post(url, json={}).json()
        assert [r["status"] for r in first["results"]] == ["succeeded", "succeeded"]
        assert first["usage"]["trip_calls_reserved"] == 2
        assert first["usage"]["llm_calls"] == 0
        assert all(not r["result"]["bookable"] for r in first["results"])
        second = client.post(url, json={}).json()
        assert [r["status"] for r in second["results"]] == ["cached", "cached"]
        assert second["usage"]["trip_calls_reserved"] == 2
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/v1/trips/{trip}").status_code == 200
        assert client.get(f"/v1/trips/{trip}/usage").json()["trip_calls_reserved"] == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"origin": "LIS"},
        {"adults": 0},
        {"adults": True},
        {"budget_amount": "-1"},
        {"budget_amount": "NaN"},
        {"passport": "secret-passport"},
        {"check_in_date": None},
        {"rooms": 3},
        {"origin": "https://evil.invalid"},
    ],
)
def test_invalid_brief_rejected_without_echoing_input(tmp_path, overrides):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = client.post("/v1/trips", json=brief_data(**overrides))
        assert response.status_code == 422
        assert "secret-passport" not in response.text


def test_invalid_searches_consume_no_allowance(tmp_path):
    with TestClient(create_app(settings_for(tmp_path, date_limit=2))) as client:
        trip = new_trip(client, flexibility_days=1)
        for offsets in ([0, 0], [2], [-1, 0, 1], [True]):
            response = client.post(f"/v1/trips/{trip}/search", json={"date_offsets": offsets})
            assert response.status_code == 422
        assert client.get(f"/v1/trips/{trip}/usage").json()["trip_calls_reserved"] == 0


def test_call_cap_and_daily_cap_across_trips(tmp_path):
    with TestClient(create_app(settings_for(tmp_path, trip_limit=1, daily_limit=1))) as client:
        trip = new_trip(client)
        result = client.post(f"/v1/trips/{trip}/search", json={}).json()
        assert sorted(r["status"] for r in result["results"]) == ["budget_exhausted", "succeeded"]
        second_trip = new_trip(client)
        result = client.post(f"/v1/trips/{second_trip}/search", json={}).json()
        assert all(r["status"] == "budget_exhausted" for r in result["results"])
        assert result["usage"]["application_calls_reserved_today"] == 1


def test_atomic_allowance_reservation_under_thread_contention(tmp_path):
    settings = settings_for(tmp_path, trip_limit=2)
    store = Store(settings.database)
    trip = store.create_trip(brief_data())

    def reserve(i):
        try:
            store.claim(str(i), trip, settings, "flights")
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(16)))
    assert sum(results) == 2
    assert store.usage(trip, settings)["trip_calls_reserved"] == 2


def test_inflight_deduplication_and_expired_cache(tmp_path):
    settings = settings_for(tmp_path)
    store = Store(settings.database)
    trip = store.create_trip(brief_data())
    call, _ = store.claim("same", trip, settings, "flights")
    with pytest.raises(SearchInProgress):
        store.claim("same", trip, settings, "flights")
    store.finish("same", call, {"valid_until": time.time() - 1}, 120, "succeeded")
    next_call, cached = store.claim("same", trip, settings, "flights")
    assert next_call != call and cached is None


def test_supplier_caching_off_even_with_existing_cache(tmp_path):
    settings = settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture")
    store = Store(settings.database)
    trip = store.create_trip(brief_data())
    call, _ = store.claim("key", trip, settings, "flights")
    store.finish("key", call, {"valid_until": time.time() + 100}, 100, "succeeded")
    second, cached = store.claim("key", trip, settings, "flights")
    assert second != call and cached is None


def test_failed_supplier_attempt_consumes_allowance_without_retry(tmp_path):
    class FailingProvider(MockProvider):
        async def search(self, operation, payload):
            raise ProviderError("Supplier search failed")

    settings = settings_for(tmp_path, trip_limit=2)
    store = Store(settings.database)
    brief = TripBrief.model_validate(brief_data())
    trip = store.create_trip(brief.model_dump(mode="json"))

    async def scenario():
        service = SearchService(store, FailingProvider(), settings)
        first = await service.run(trip, brief, SearchRequest())
        second = await service.run(trip, brief, SearchRequest())
        assert all(r["status"] == "provider_error" for r in first["results"])
        assert all(r["status"] == "budget_exhausted" for r in second["results"])

    asyncio.run(scenario())
    assert store.usage(trip, settings)["trip_calls_reserved"] == 2


def test_concurrency_bound(tmp_path):
    class CountingProvider(MockProvider):
        active = 0
        peak = 0

        async def search(self, operation, payload):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return await super().search(operation, payload)

    settings = settings_for(tmp_path, concurrency=2)
    store = Store(settings.database)
    brief = TripBrief.model_validate(brief_data())
    trip = store.create_trip(brief.model_dump(mode="json"))
    provider = CountingProvider()

    async def scenario():
        result = await SearchService(store, provider, settings).run(
            trip,
            brief,
            SearchRequest(date_offsets=[-1, 0, 1]),
        )
        assert len(result["results"]) == 6

    asyncio.run(scenario())
    assert provider.peak == 2


@pytest.mark.parametrize(
    "values",
    [
        {"provider": "live"},
        {"provider": "duffel_sandbox", "token": "duffel_live_secret"},
        {"provider": "duffel_sandbox"},
        {"trip_limit": 0},
    ],
)
def test_unsafe_configuration_rejected(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_api_key_and_no_transaction_endpoints(tmp_path):
    settings = settings_for(tmp_path, api_key="local-fixture-secret")
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/providers").status_code == 401
        response = client.get(
            "/v1/providers", headers={"Authorization": "Bearer local-fixture-secret"}
        )
        assert response.status_code == 200
        assert "local-fixture-secret" not in response.text
        assert client.get("/health").json()["payment_enabled"] is False
        for endpoint in ("/v1/bookings", "/v1/payments", "/v1/holds"):
            assert client.post(endpoint, json={}).status_code == 404
        assert (
            client.get(
                "/v1/trips/missing/usage", headers={"Authorization": "Bearer local-fixture-secret"}
            ).status_code
            == 404
        )


def test_flight_adapter_payload_headers_and_sandbox_response(tmp_path):
    seen = []
    expiry = (datetime.now(UTC) + timedelta(minutes=3)).isoformat()

    def handler(request):
        seen.append(request)
        assert request.url.path == "/air/offer_requests"
        assert request.headers["Duffel-Version"] == "v2"
        assert request.headers["Authorization"] == "Bearer duffel_test_fixture"
        assert json.loads(request.content)["data"]["slices"][0]["origin"] == "LHR"
        assert int(request.url.params["supplier_timeout"]) < 12000
        return httpx.Response(
            200,
            json={
                "data": {
                    "live_mode": False,
                    "offers": [
                        {
                            "id": "off_fixture",
                            "total_amount": "123.45",
                            "total_currency": "GBP",
                            "expires_at": expiry,
                            "slices": [],
                        },
                    ],
                }
            },
            headers={"x-request-id": "req_fixture"},
        )

    async def scenario():
        provider = DuffelSandboxProvider(
            settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture"),
            transport=httpx.MockTransport(handler),
        )
        try:
            brief = TripBrief.model_validate(brief_data())
            payload = jobs_for(brief, SearchRequest(), 3)[0][2]
            result = await provider.search("flights", payload)
            assert result["offers"][0]["amount"] == "123.45"
            assert result["request_id"] == "req_fixture"
            assert not result["bookable"]
            with pytest.raises(ProviderError):
                await provider.search("payments", {})
        finally:
            await provider.close()

    asyncio.run(scenario())
    assert len(seen) == 1


def test_stay_adapter_uses_documented_response_without_live_mode_field(tmp_path):
    def handler(request):
        assert request.url.path == "/stays/search"
        return httpx.Response(
            200,
            json={
                "data": {
                    "results": [
                        {
                            "id": "srr_fixture",
                            "cheapest_rate_total_amount": "799.00",
                            "cheapest_rate_currency": "GBP",
                            "accommodation": {"name": "Fixture hotel"},
                            "expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
                        }
                    ]
                }
            },
        )

    async def scenario():
        provider = DuffelSandboxProvider(
            settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture"),
            transport=httpx.MockTransport(handler),
        )
        try:
            result = await provider.search("stays", {})
            assert result["offers"][0]["accommodation"] == "Fixture hotel"
            assert result["valid_until"] <= time.time() + 61
        finally:
            await provider.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"errors": [{"message": "duffel_test_secret-never-echo"}]}),
        (200, {"data": {"live_mode": True, "offers": []}}),
        (200, {"data": {"live_mode": False, "offers": [{"id": "broken"}]}}),
    ],
)
def test_supplier_errors_are_sanitized_and_not_retried(tmp_path, status, body):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status, json=body)

    async def scenario():
        provider = DuffelSandboxProvider(
            settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture"),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ProviderError) as error:
                await provider.search("flights", {})
            assert "secret-never-echo" not in str(error.value)
        finally:
            await provider.close()

    asyncio.run(scenario())
    assert count == 1


def test_timeout_is_not_retried(tmp_path):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("secret-internal-data")

    async def scenario():
        provider = DuffelSandboxProvider(
            settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture"),
            transport=httpx.MockTransport(handler),
        )
        try:
            with pytest.raises(ProviderError, match="could not be reached"):
                await provider.search("flights", {})
        finally:
            await provider.close()

    asyncio.run(scenario())
    assert calls == 1
