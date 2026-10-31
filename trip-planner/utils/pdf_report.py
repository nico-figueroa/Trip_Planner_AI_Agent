"""PDF export for generated itineraries."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fpdf import FPDF

# fpdf2 core fonts only support Latin-1, so common typographic characters are mapped first.
_TYPOGRAPHIC_REPLACEMENTS = str.maketrans(
    {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2022": "-",
        "\u00a0": " ",
    }
)


def _text(value: Any) -> str:
    text = str(value or "").translate(_TYPOGRAPHIC_REPLACEMENTS)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def day_heading(plan: dict[str, Any], day: dict[str, Any]) -> str:
    """Return a day label, including its calendar date when the plan has a start date."""
    number = day.get("day")
    label = f"Day {number if number is not None else '?'}"
    try:
        start = date.fromisoformat(str(plan.get("start_date")))
        if isinstance(number, int) and not isinstance(number, bool) and number >= 1:
            label += f" · {start + timedelta(days=number - 1):%a %b %d, %Y}"
    except ValueError:
        pass
    return f"{label}: {day.get('title', 'Activities')}"


class _ItineraryPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120)
        self.cell(0, 6, f"AI Trip Planner - page {self.page_no()}", align="C")


def build_itinerary_pdf(plan: dict[str, Any]) -> bytes:
    """Render an itinerary plan dictionary as a printable PDF report."""
    itinerary = plan.get("itinerary")
    if not isinstance(itinerary, dict):
        itinerary = {}
    pdf = _ItineraryPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    def heading(text: str, size: int = 13) -> None:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", size)
        pdf.set_text_color(30)
        pdf.multi_cell(0, size * 0.55, _text(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def paragraph(text: Any, style: str = "", size: int = 10) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(50)
        pdf.multi_cell(0, 5, _text(text), new_x="LMARGIN", new_y="NEXT")

    heading(itinerary.get("destination") or plan.get("destination") or "Itinerary", 18)
    details = [
        f"Duration: {plan.get('duration')} days" if plan.get("duration") else "",
        f"Starts: {plan.get('start_date')}" if plan.get("start_date") else "",
        f"Interests: {plan.get('interests')}" if plan.get("interests") else "",
        f"Budget: {plan.get('budget')}" if plan.get("budget") else "",
        f"Created: {str(plan.get('created_at', ''))[:10]}" if plan.get("created_at") else "",
    ]
    if any(details):
        paragraph("  |  ".join(item for item in details if item), "I", 9)
    if itinerary.get("overview"):
        heading("Overview")
        paragraph(itinerary["overview"])

    daily_plan = itinerary.get("daily_plan")
    if isinstance(daily_plan, list) and daily_plan:
        heading("Daily plan")
        for day in daily_plan:
            if not isinstance(day, dict):
                continue
            paragraph(day_heading(plan, day), "B", 11)
            activities = day.get("activities")
            for activity in activities if isinstance(activities, list) else []:
                if isinstance(activity, str):
                    paragraph(f"  - {activity}")
            pdf.ln(2)

    if itinerary.get("travel_notes"):
        heading("Travel notes")
        paragraph(itinerary["travel_notes"])

    pois = [poi for poi in plan.get("pois") or [] if isinstance(poi, dict)]
    if pois:
        heading("Nearby places")
        for poi in pois:
            line = f"{poi.get('name', 'Place')} ({poi.get('category', 'Place')})"
            if poi.get("address"):
                line += f" - {poi['address']}"
            paragraph(f"  - {line}", size=9)
        pdf.ln(2)
        paragraph(
            "Places powered by Geoapify using OpenStreetMap data "
            "(c) OpenStreetMap contributors.",
            "I",
            8,
        )

    return bytes(pdf.output())
