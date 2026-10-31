from utils.validation import (
    validate_trip_request
)


def test_valid_request():

    errors = validate_trip_request(
        "Seattle",
        3
    )

    assert len(errors) == 0


def test_missing_destination():

    errors = validate_trip_request(
        "",
        3
    )

    assert len(errors) > 0