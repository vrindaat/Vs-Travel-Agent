import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from travel_agent.config import Settings
from travel_agent.models import SearchRequest, TripBrief
from travel_agent.providers import DuffelSandboxProvider, MockProvider
from travel_agent.service import SearchService
from travel_agent.store import Store


def create_app(settings: Settings | None = None, provider=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        store = Store(settings.database)
        supplier = provider or (
            MockProvider() if settings.provider == "mock" else DuffelSandboxProvider(settings)
        )
        app.state.store = store
        app.state.service = SearchService(store, supplier, settings)
        try:
            yield
        finally:
            await supplier.close()

    app = FastAPI(title="VS Travel Agent - supplier discovery", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        # Validation errors normally echo inputs. Remove them to avoid returning sensitive fields.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )

    def authorize(authorization: Annotated[str | None, Header()] = None):
        if settings.api_key and not secrets.compare_digest(
            (authorization or "").encode(),
            f"Bearer {settings.api_key}".encode(),
        ):
            raise HTTPException(status_code=401, detail="Valid API bearer key required")

    def brief_for(trip_id):
        brief = app.state.store.get_trip(trip_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        return TripBrief.model_validate(brief, context={"stored_brief": True})

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "provider": settings.provider,
            "live_booking_enabled": False,
            "payment_enabled": False,
        }

    @app.get("/v1/providers", dependencies=[Depends(authorize)])
    def providers():
        return {
            "selected": settings.provider,
            "mode": "offline_fixtures" if settings.provider == "mock" else "sandbox_only",
            "token_configured": bool(settings.token),
            "operations": ["flight_search", "stay_search"],
            "live_access_verified": False,
            "stays_access_verified": False,
            "llm_required": False,
            "supplier_cache_enabled": settings.supplier_cache,
            "deployment_scope": "local_single_user_development",
        }

    @app.post("/v1/trips", status_code=201, dependencies=[Depends(authorize)])
    def create_trip(brief: TripBrief):
        trip_id = app.state.store.create_trip(brief.model_dump(mode="json"))
        return {"trip_id": trip_id, "brief": brief.model_dump(mode="json")}

    @app.get("/v1/trips/{trip_id}", dependencies=[Depends(authorize)])
    def get_trip(trip_id: str):
        return {"trip_id": trip_id, "brief": brief_for(trip_id).model_dump(mode="json")}

    @app.post("/v1/trips/{trip_id}/search", dependencies=[Depends(authorize)])
    async def search(trip_id: str, request: SearchRequest):
        brief = brief_for(trip_id)
        try:
            return await app.state.service.run(trip_id, brief, request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/v1/trips/{trip_id}/usage", dependencies=[Depends(authorize)])
    def usage(trip_id: str):
        brief_for(trip_id)
        return app.state.store.usage(trip_id, settings)

    @app.get("/v1/trips/{trip_id}/attempts", dependencies=[Depends(authorize)])
    def attempts(trip_id: str):
        brief_for(trip_id)
        return {"trip_id": trip_id, "attempts": app.state.store.attempts(trip_id)}

    return app
