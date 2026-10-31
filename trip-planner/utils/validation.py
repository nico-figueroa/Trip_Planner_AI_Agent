def validate_trip_request(
    destination: str,
    duration: int
):

    errors = []

    if not destination.strip():
        errors.append(
            "Destination is required."
        )

    if duration < 1:
        errors.append(
            "Duration must be at least 1 day."
        )

    return errors