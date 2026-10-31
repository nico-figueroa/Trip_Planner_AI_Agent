"""Validated models for the planner's structured output."""

from pydantic import BaseModel, ConfigDict, Field


class DayPlan(BaseModel):
    """Activities for one day of a trip."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    day: int = Field(ge=1)
    title: str = Field(min_length=1)
    activities: list[str] = Field(min_length=1)


class Itinerary(BaseModel):
    """The public itinerary shape returned by the AI planner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str = Field(min_length=1)
    overview: str = Field(min_length=1)
    travel_notes: str = Field(min_length=1)
    daily_plan: list[DayPlan] = Field(min_length=1, max_length=30)
