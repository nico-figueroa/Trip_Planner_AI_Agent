"""Validated models for trip planning and structured itinerary output."""

from pydantic import BaseModel, ConfigDict, Field # Pydantic classes for defining and validating data models

# Pydantic models for validating the structured output of the trip planner
class DayPlan(BaseModel):
    """Activities for one day of a trip."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    day: int = Field(ge=1)
    title: str = Field(min_length=1)
    activities: list[str] = Field(min_length=1)
    locations: list[str] = Field(default_factory=list, max_length=12)
    estimated_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)

# Pydantic model for a single day's plan within the itinerary
class Itinerary(BaseModel):
    """The public itinerary shape returned by the AI planner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str = Field(min_length=1)
    overview: str = Field(min_length=1)
    travel_notes: str = Field(min_length=1)
    daily_plan: list[DayPlan] = Field(min_length=1, max_length=30)
