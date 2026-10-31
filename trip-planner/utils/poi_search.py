import requests

from utils.config import (
    OVERPASS_URL,
    USER_AGENT
)


def find_nearby_pois(
    latitude: float,
    longitude: float,
    radius: int = 3000
):

    query = f"""
    [out:json];
    (
      node
        ["tourism"]
        (around:{radius},{latitude},{longitude});
    );
    out body;
    """

    headers = {
        "User-Agent": USER_AGENT
    }

    try:

        response = requests.post(
            OVERPASS_URL,
            data=query,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        pois = []

        for item in data.get(
            "elements",
            []
        )[:20]:

            pois.append({
                "name":
                    item.get(
                        "tags",
                        {}
                    ).get(
                        "name",
                        "Unknown"
                    ),
                "latitude":
                    item.get(
                        "lat"
                    ),
                "longitude":
                    item.get(
                        "lon"
                    )
            })

        return pois

    except Exception as error:

        print(
            f"POI search failed: {error}"
        )

        return []