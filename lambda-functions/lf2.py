import json
import os
from datetime import datetime, timezone

import boto3
import urllib3

sqs = boto3.client("sqs")
ses = boto3.client("ses")
table = boto3.resource("dynamodb").Table("yelp-restaurants")
# Extra credit: remembers each user's last search
state_table = boto3.resource("dynamodb").Table(
    os.environ.get("STATE_TABLE", "user-search-state"))
http = urllib3.PoolManager()

QUEUE_URL = os.environ["QUEUE_URL"]
OS_HOST = os.environ["OS_HOST"]
SENDER = os.environ["SENDER_EMAIL"]
HEADERS = {
    **urllib3.make_headers(basic_auth=f'{os.environ["OS_USER"]}:{os.environ["OS_PASS"]}'),
    "Content-Type": "application/json",
}


def random_restaurant_ids(cuisine, n=3):
    """Get n random restaurant IDs for a cuisine from OpenSearch."""
    query = {
        "size": n,
        "query": {
            "function_score": {
                "query": {"match": {"Cuisine": cuisine}},
                "random_score": {},
            }
        },
    }
    r = http.request("POST", f"{OS_HOST}/restaurants/_search",
                     body=json.dumps(query), headers=HEADERS)
    hits = json.loads(r.data)["hits"]["hits"]
    return [h["_source"]["RestaurantID"] for h in hits]


def get_details(ids):
    """Fetch full restaurant details from DynamoDB."""
    items = [table.get_item(Key={"BusinessID": i}).get("Item") for i in ids]
    return [i for i in items if i]


def build_email(req, restaurants):
    lines = [f"{n}. {r.get('Name')}, located at {r.get('Address')}"
             for n, r in enumerate(restaurants, 1)]
    cuisine = req["Cuisine"].title()

    if req.get("ReuseLast"):
        intro = (f"Welcome back! Here are the same {cuisine} restaurant "
                 f"suggestions you received last time:")
    else:
        date = datetime.strptime(
            req["DiningDate"], "%Y-%m-%d").strftime("%A, %B %-d")
        time = datetime.strptime(
            req["DiningTime"], "%H:%M").strftime("%-I:%M %p")
        intro = (f"Hello! Here are my {cuisine} restaurant suggestions for "
                 f"{req['NumberOfPeople']} people, for {date} at {time}:")

    return intro + "\n\n" + "\n".join(lines) + "\n\nEnjoy your meal!"


def save_state(req, restaurants):
    """Extra credit: remember this user's last search and results."""
    request = {k: req[k] for k in
               ("Location", "Cuisine", "DiningDate",
                "DiningTime", "NumberOfPeople", "Email")
               if req.get(k)}
    state_table.put_item(Item={
        "UserID": req["UserID"],
        "Location": req.get("Location", "").lower(),
        "Cuisine": req["Cuisine"].lower(),
        "Request": request,
        "Restaurants": [{"Name": r.get("Name"), "Address": r.get("Address")}
                        for r in restaurants],
        "UpdatedAt": datetime.now(timezone.utc).isoformat(),
    })


def lambda_handler(event, context):
    msgs = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10,
                               WaitTimeSeconds=1).get("Messages", [])
    for m in msgs:
        try:
            req = json.loads(m["Body"])
            if req.get("ReuseLast") and req.get("Restaurants"):
                restaurants = req["Restaurants"]  # same as last time
            else:
                restaurants = get_details(
                    random_restaurant_ids(req["Cuisine"]))
            ses.send_email(
                Source=SENDER,
                Destination={"ToAddresses": [req["Email"]]},
                Message={
                    "Subject": {"Data": f"Your {req['Cuisine'].title()} restaurant suggestions"},
                    "Body": {"Text": {"Data": build_email(req, restaurants)}},
                },
            )
            if req.get("UserID"):
                save_state(req, restaurants)
            sqs.delete_message(QueueUrl=QUEUE_URL,
                               ReceiptHandle=m["ReceiptHandle"])
            print("Sent suggestions to", req["Email"])
        except Exception as e:
            print("Failed on message:", m["Body"], e)
    return {"processed": len(msgs)}
