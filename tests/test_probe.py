import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.test_backend import brief_data, new_trip, settings_for
from travel_agent import probe as probe_module
from travel_agent.api import create_app
from travel_agent.models import TripBrief
from travel_agent.probe import ProbeError, main, probe
from travel_agent.providers import DuffelSandboxProvider
from travel_agent.store import Store


@pytest.mark.parametrize("operation", ["flights", "stays"])
def test_explicit_operation_consumes_only_one_allowance(tmp_path, operation):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        trip_id = new_trip(client)
        response = client.post(f"/v1/trips/{trip_id}/search", json={"operations": [operation]})
        assert response.status_code == 200
        result = response.json()
        assert [row["operation"] for row in result["results"]] == [operation]
        assert result["usage"]["trip_calls_reserved"] == 1


@pytest.mark.parametrize("operations", [[], ["flights", "flights"], ["payments"], "flights"])
def test_invalid_operations_do_not_consume_allowance(tmp_path, operations):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        trip_id = new_trip(client)
        response = client.post(f"/v1/trips/{trip_id}/search", json={"operations": operations})
        assert response.status_code == 422
        assert client.get(f"/v1/trips/{trip_id}/usage").json()["trip_calls_reserved"] == 0


def test_hotel_search_without_hotel_brief_rejected_before_calls(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        trip_id = new_trip(client, stay_location=None, check_in_date=None, check_out_date=None)
        response = client.post(f"/v1/trips/{trip_id}/search", json={"operations": ["stays"]})
        assert response.status_code == 422
        assert client.get(f"/v1/trips/{trip_id}/usage").json()["trip_calls_reserved"] == 0


def stored_trip(settings):
    store = Store(settings.database)
    brief = TripBrief.model_validate(brief_data())
    return store, store.create_trip(brief.model_dump(mode="json"))


def test_preview_and_stays_gate_never_construct_supplier(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture")
    store, trip_id = stored_trip(settings)

    def forbidden(*args):
        pytest.fail("Preview/access gate must not construct a supplier")

    monkeypatch.setattr(probe_module, "DuffelSandboxProvider", forbidden)
    report = asyncio.run(probe(settings, trip_id, "flights"))
    assert report["mode"] == "preview"
    assert report["max_outbound_attempts"] == 1
    assert len(report["search_payload"]["slices"]) == 2
    assert "duffel_test_fixture" not in json.dumps(report)
    with pytest.raises(ProbeError, match="Confirm Stays access"):
        asyncio.run(probe(settings, trip_id, "stays", execute=True))
    assert store.usage(trip_id, settings)["trip_calls_reserved"] == 0
    assert store.attempts(trip_id) == []


@pytest.mark.parametrize("operation", ["flights", "stays"])
def test_bounded_probe_with_transport_fixture_preserves_currency_and_request_id(
    tmp_path, monkeypatch, operation
):
    settings = settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture")
    store, trip_id = stored_trip(settings)
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if operation == "flights":
            data = {
                "live_mode": False,
                "offers": [{"id": "off_test", "total_amount": "123.45", "total_currency": "GBP"}],
            }
        else:
            data = {
                "results": [
                    {
                        "id": "srr_test",
                        "cheapest_rate_total_amount": "700.00",
                        "cheapest_rate_currency": "EUR",
                    }
                ]
            }
        return httpx.Response(200, json={"data": data}, headers={"x-request-id": "req_test"})

    monkeypatch.setattr(
        probe_module,
        "DuffelSandboxProvider",
        lambda settings: DuffelSandboxProvider(settings, transport=httpx.MockTransport(handler)),
    )
    report = asyncio.run(
        probe(settings, trip_id, operation, execute=True, stays_access_confirmed=True)
    )
    assert seen == [DuffelSandboxProvider.SEARCH_PATHS[operation]]
    assert report["status"] == "succeeded"
    assert report["source"] == "supplier_sandbox"  # Fixture transport; no real account verified.
    assert report["request_id"] == "req_test"
    assert report["normalized_offer_count"] == 1
    assert report["currencies_observed"] == (["GBP"] if operation == "flights" else ["EUR"])
    assert report["requested_budget_currency"] == "USD"
    assert report["production_access_verified"] is False
    assert report["usage_after"]["trip_calls_reserved"] == 1
    restarted = Store(settings.database)
    assert restarted.attempts(trip_id)[0]["request_id"] == "req_test"
    with store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM search_cache WHERE payload IS NOT NULL").fetchone()[0]
            == 0
        )
    with TestClient(create_app(settings_for(tmp_path, api_key="local-key"))) as client:
        url = f"/v1/trips/{trip_id}/attempts"
        assert client.get(url).status_code == 401
        response = client.get(url, headers={"Authorization": "Bearer local-key"})
        assert response.json()["attempts"][0]["request_id"] == "req_test"
        assert "123.45" not in response.text and "duffel_test_fixture" not in response.text
        assert (
            client.get(
                "/v1/trips/missing/attempts", headers={"Authorization": "Bearer local-key"}
            ).status_code
            == 404
        )


def test_cli_failure_exit_and_sanitized_configuration_error(tmp_path, monkeypatch, capsys):
    settings = settings_for(tmp_path)
    store, trip_id = stored_trip(settings)
    monkeypatch.setattr(probe_module.Settings, "from_env", lambda: settings)
    assert main(["--trip-id", trip_id]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "preview"
    assert store.attempts(trip_id) == []
    assert main(["--trip-id", trip_id, "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "synthetic_fixture"
    assert main(["--trip-id", "missing"]) == 2
    capsys.readouterr()

    def bad_settings():
        raise ValueError("duffel_live_secret_must_not_leak")

    monkeypatch.setattr(probe_module.Settings, "from_env", bad_settings)
    assert main(["--trip-id", trip_id, "--execute"]) == 2
    assert "duffel_live_secret" not in capsys.readouterr().out


def test_malformed_response_request_id_is_durable_and_probe_does_not_retry(tmp_path, monkeypatch):
    settings = settings_for(tmp_path, provider="duffel_sandbox", token="duffel_test_fixture")
    store, trip_id = stored_trip(settings)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"data": {"live_mode": False, "offers": [{"id": "broken"}]}},
            headers={"x-request-id": "req_malformed"},
        )

    monkeypatch.setattr(
        probe_module,
        "DuffelSandboxProvider",
        lambda settings: DuffelSandboxProvider(settings, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(probe_module.Settings, "from_env", lambda: settings)
    assert main(["--trip-id", trip_id, "--execute"]) == 1
    assert len(calls) == 1
    assert store.attempts(trip_id)[0]["request_id"] == "req_malformed"
    assert store.attempts(trip_id)[0]["status"] == "failed"


def test_probe_cannot_bypass_existing_trip_allowance(tmp_path, monkeypatch, capsys):
    settings = settings_for(tmp_path, trip_limit=1)
    store, trip_id = stored_trip(settings)
    call_id, _ = store.claim("previous", trip_id, settings, "stays")
    store.finish("previous", call_id, None, 0, "failed")
    monkeypatch.setattr(probe_module.Settings, "from_env", lambda: settings)
    assert main(["--trip-id", trip_id, "--execute"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "budget_exhausted"
    assert len(store.attempts(trip_id)) == 1
