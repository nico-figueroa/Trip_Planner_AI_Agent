from utils.geocoding import geocode_city
from utils.poi_search import find_nearby_pois
from utils.rag import get_destination_context


class TripPlannerAgent:
    """
    Orchestrates tool calls and generates
    itinerary context.
    """

    def generate_trip_plan(
        self,
        destination: str,
        duration: int,
        interests: str
    ):

        result = {
            "destination": destination,
            "duration": duration,
            "interests": interests,
            "location": None,
            "pois": [],
            "travel_context": "",
            "itinerary": []
        }

        # Step 1
        location = geocode_city(destination)

        if not location:
            raise ValueError(
                f"Unable to geocode destination: {destination}"
            )

        result["location"] = location

        # Step 2
        pois = find_nearby_pois(
            location["latitude"],
            location["longitude"]
        )

        result["pois"] = pois

        # Step 3
        result["travel_context"] = (
            get_destination_context(destination)
        )

        # Step 4
        result["itinerary"] = (
            self._create_basic_itinerary(
                destination,
                duration,
                interests,
                pois
            )
        )

        return result

    def _create_basic_itinerary(
        self,
        destination,
        duration,
        interests,
        pois
    ):

        itinerary = []

        for day in range(1, duration + 1):

            itinerary.append(
                {
                    "day": day,
                    "title": f"Day {day}",
                    "activities": [
                        f"Explore {destination}",
                        f"Focus on {interests}"
                    ]
                }
            )

        return itinerary