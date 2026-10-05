import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import requests
from dotenv import load_dotenv


# -----------------------------
# Configuration
# -----------------------------

load_dotenv()

YELP_API_KEY = os.getenv("YELP_API_KEY")

if not YELP_API_KEY:
    raise ValueError("YELP_API_KEY was not found in .env")


YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"

CUISINES = [
    "Chinese",
    "Italian",
    "Indian",
    "Japanese",
    "Mexican"
]

# We want 200 unique restaurants for every cuisine.
TARGET_PER_CUISINE = 200

# Different Manhattan searches give us a larger candidate pool.
MANHATTAN_LOCATIONS = [
    "Manhattan, New York, NY",
    "Upper East Side, New York, NY",
    "Upper West Side, New York, NY",
    "Midtown Manhattan, New York, NY",
    "Lower Manhattan, New York, NY",
    "East Village, New York, NY",
    "West Village, New York, NY",
    "Harlem, New York, NY",
    "Chelsea, New York, NY",
    "SoHo, New York, NY"
]

headers = {
    "Authorization": f"Bearer {YELP_API_KEY}"
}


# -----------------------------
# DynamoDB connection
# -----------------------------

dynamodb = boto3.resource(
    "dynamodb",
    region_name="us-east-1"
)

table = dynamodb.Table("yelp-restaurants")


# Prevent duplicate Yelp businesses across the entire database.
seen_business_ids = set()

total_inserted = 0


# -----------------------------
# Yelp search
# -----------------------------

def search_yelp(cuisine, location):
    """
    Get up to 200 candidates from one Yelp search.

    Yelp returns at most 50 businesses per individual request,
    so we request four pages.
    """

    restaurants = []

    for offset in [0, 50, 100, 150]:

        params = {
            "term": f"{cuisine} restaurants",
            "location": location,
            "limit": 50,
            "offset": offset
        }

        response = requests.get(
            YELP_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        businesses = response.json().get("businesses", [])

        if not businesses:
            break

        restaurants.extend(businesses)

        time.sleep(0.2)

    return restaurants


# -----------------------------
# Collect each cuisine
# -----------------------------

for cuisine in CUISINES:

    print(f"\nCollecting {cuisine} restaurants...")

    cuisine_inserted = 0

    with table.batch_writer() as batch:

        for search_location in MANHATTAN_LOCATIONS:

            if cuisine_inserted >= TARGET_PER_CUISINE:
                break

            print(f"  Searching: {search_location}")

            businesses = search_yelp(
                cuisine,
                search_location
            )

            for business in businesses:

                if cuisine_inserted >= TARGET_PER_CUISINE:
                    break

                business_id = business.get("id")

                if not business_id:
                    continue

                # Do not store the same Yelp business twice.
                if business_id in seen_business_ids:
                    continue

                location = business.get("location", {})
                coordinates = business.get("coordinates", {})

                latitude = coordinates.get("latitude")
                longitude = coordinates.get("longitude")

                # Skip incomplete records.
                if latitude is None or longitude is None:
                    continue

                restaurant = {
                    "BusinessID": business_id,

                    "Name": business.get(
                        "name",
                        ""
                    ),

                    "Address": ", ".join(
                        location.get(
                            "display_address",
                            []
                        )
                    ),

                    "Coordinates": {
                        "Latitude": Decimal(
                            str(latitude)
                        ),
                        "Longitude": Decimal(
                            str(longitude)
                        )
                    },

                    "NumberReviews": business.get(
                        "review_count",
                        0
                    ),

                    "Rating": Decimal(
                        str(
                            business.get(
                                "rating",
                                0
                            )
                        )
                    ),

                    "ZipCode": location.get(
                        "zip_code",
                        ""
                    ),

                    "Cuisine": cuisine,

                    "insertedAtTimestamp": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    )
                }

                batch.put_item(
                    Item=restaurant
                )

                seen_business_ids.add(
                    business_id
                )

                cuisine_inserted += 1
                total_inserted += 1

    print(
        f"Inserted {cuisine_inserted} unique "
        f"{cuisine} restaurants."
    )

    if cuisine_inserted < TARGET_PER_CUISINE:
        print(
            f"WARNING: Only found "
            f"{cuisine_inserted} unique "
            f"{cuisine} restaurants."
        )


# -----------------------------
# Final result
# -----------------------------

print("\n================================")
print("IMPORT COMPLETE")
print("================================")
print(
    f"Total unique restaurants inserted: "
    f"{total_inserted}"
)
print("================================")
