import os
from dataclasses import dataclass, field
from pathlib import Path


def number(name, default, low, high):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    token: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    database: Path = Path("data/travel.sqlite3")
    trip_limit: int = 12
    daily_limit: int = 60
    date_limit: int = 3
    concurrency: int = 2
    timeout: int = 12
    cache_ttl: int = 120
    supplier_cache: bool = False

    def __post_init__(self):
        if self.provider not in {"mock", "duffel_sandbox"}:
            raise ValueError("Provider must be mock or duffel_sandbox; live mode is disabled")
        if self.provider == "duffel_sandbox" and not self.token.startswith("duffel_test_"):
            raise ValueError("Sandbox requires a duffel_test_ credential; live tokens are rejected")
        for name in (
            "trip_limit",
            "daily_limit",
            "date_limit",
            "concurrency",
            "timeout",
            "cache_ttl",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def from_env(cls):
        cache = os.getenv("ALLOW_SUPPLIER_CACHE", "false").lower()
        if cache not in {"true", "false"}:
            raise ValueError("ALLOW_SUPPLIER_CACHE must be true or false")
        return cls(
            provider=os.getenv("TRAVEL_PROVIDER", "mock"),
            token=os.getenv("DUFFEL_ACCESS_TOKEN", ""),
            api_key=os.getenv("TRAVEL_API_KEY", ""),
            database=Path(os.getenv("TRAVEL_DATABASE", "data/travel.sqlite3")),
            trip_limit=number("MAX_PROVIDER_CALLS_PER_TRIP", 12, 1, 1000),
            daily_limit=number("MAX_PROVIDER_CALLS_PER_DAY", 60, 1, 10000),
            date_limit=number("MAX_DATE_OPTIONS", 3, 1, 7),
            concurrency=number("MAX_CONCURRENT_PROVIDER_CALLS", 2, 1, 8),
            timeout=number("PROVIDER_TIMEOUT_SECONDS", 12, 5, 60),
            cache_ttl=number("CACHE_TTL_SECONDS", 120, 1, 300),
            supplier_cache=cache == "true",
        )
