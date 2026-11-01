from utils.pdf_report import build_itinerary_pdf


def test_pdf_report_renders_itinerary_with_unicode_text():
    pdf = build_itinerary_pdf(
        {
            "destination": "Limón",
            "duration": 1,
            "created_at": "2026-10-31T12:00:00+00:00",
            "pois": [{"name": "Café — Central", "category": "Cafe", "address": "Calle 1"}],
            "itinerary": {
                "destination": "Limón, Costa Rica",
                "overview": "Caribbean coast “highlights” 東京",
                "travel_notes": "Bring sunscreen.",
                "daily_plan": [{"day": 1, "title": "Beach", "activities": ["Swim"]}],
            },
        }
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_pdf_report_tolerates_legacy_plan_shapes():
    assert build_itinerary_pdf({"itinerary": None, "pois": "invalid"}).startswith(b"%PDF")


def test_day_heading_includes_calendar_date_only_when_start_date_is_known():
    from utils.pdf_report import day_heading

    day = {"day": 4, "title": "Christmas Eve dinner"}

    assert day_heading({"start_date": "2026-12-21"}, day) == (
        "Day 4 · Thu Dec 24, 2026: Christmas Eve dinner"
    )
    assert day_heading({"start_date": None}, day) == "Day 4: Christmas Eve dinner"
    assert build_itinerary_pdf(
        {"start_date": "2026-12-21", "itinerary": {"daily_plan": [day]}}
    ).startswith(b"%PDF")


def test_unset_pdf_budget_does_not_report_negative_remaining(monkeypatch):
    from utils import pdf_report

    paragraphs = []
    original = pdf_report._ItineraryPDF.multi_cell

    def capture(self, width, height, text, *args, **kwargs):
        paragraphs.append(text)
        return original(self, width, height, text, *args, **kwargs)

    monkeypatch.setattr(pdf_report._ItineraryPDF, "multi_cell", capture)
    pdf = build_itinerary_pdf({
        "budget_total": "0", "currency": "USD",
        "expenses": [{"day": 1, "category": "Food", "amount": "10", "description": "Lunch"}],
        "itinerary": {"daily_plan": [{"day": 1, "estimated_cost": 20.0}]},
    })
    assert pdf.startswith(b"%PDF")
    assert any("total budget not set" in text for text in paragraphs)
    assert not any("Remaining budget:" in text for text in paragraphs)
