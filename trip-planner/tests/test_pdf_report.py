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
