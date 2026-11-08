from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    model_validator,
)

Airport = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class StayLocation(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: int = Field(default=3, ge=1, le=10, strict=True)


class TripBrief(StrictModel):
    origin: Airport
    destination: Airport
    departure_date: date
    return_date: date
    adults: int = Field(default=1, ge=1, le=8, strict=True)
    rooms: int = Field(default=1, ge=1, le=4, strict=True)
    budget_amount: Decimal = Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)
    budget_currency: Currency = "USD"
    flexibility_days: int = Field(default=0, ge=0, le=3, strict=True)
    stay_location: StayLocation | None = None
    # Explicit hotel dates avoid assuming an overnight flight arrives on departure day.
    check_in_date: date | None = None
    check_out_date: date | None = None

    @model_validator(mode="after")
    def validate_trip(self, info: ValidationInfo):
        if self.origin == self.destination:
            raise ValueError("Origin and destination must differ")
        if (
            not (info.context or {}).get("stored_brief")
            and self.departure_date < datetime.now(UTC).date()
        ):
            raise ValueError("Departure must be today or later")
        if not timedelta(days=1) <= self.return_date - self.departure_date <= timedelta(days=30):
            raise ValueError("Trip length must be between 1 and 30 days")
        if self.rooms > self.adults:
            raise ValueError("Rooms cannot exceed adults in this adults-only pilot")
        if self.stay_location:
            if self.check_in_date is None or self.check_out_date is None:
                raise ValueError("Hotel search requires explicit check-in and check-out dates")
            if not (
                self.departure_date <= self.check_in_date < self.check_out_date <= self.return_date
            ):
                raise ValueError("Hotel dates must be ordered and inside the trip window")
        elif self.check_in_date is not None or self.check_out_date is not None:
            raise ValueError("Hotel dates require stay_location")
        return self


class SearchRequest(StrictModel):
    # None preserves the original behavior: flights plus stays when supplied in the brief.
    operations: list[Literal["flights", "stays"]] | None = Field(
        default=None, min_length=1, max_length=2
    )
    date_offsets: list[Annotated[int, Field(ge=-3, le=3, strict=True)]] = Field(
        default_factory=lambda: [0],
        min_length=1,
        max_length=7,
    )

    @model_validator(mode="after")
    def unique_offsets(self):
        if len(self.date_offsets) != len(set(self.date_offsets)):
            raise ValueError("Date offsets must be unique")
        if self.operations is not None and len(self.operations) != len(set(self.operations)):
            raise ValueError("Search operations must be unique")
        return self
