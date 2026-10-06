import json
import os
from datetime import datetime

import boto3
import urllib3

sqs = boto3.client("sqs")
ses = boto3.client("ses")
table = boto3.resource("dynamodb").Table("yelp-restaurants")
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
    date = datetime.strptime(
        req["DiningDate"], "%Y-%m-%d").strftime("%A, %B %-d")
    time = datetime.strptime(req["DiningTime"], "%H:%M").strftime("%-I:%M %p")
    lines = [f"{n}. {r.get('Name')}, located at {r.get('Address')}"
             for n, r in enumerate(restaurants, 1)]
    return (f"Hello! Here are my {req['Cuisine'].title()} restaurant suggestions for "
            f"{req['NumberOfPeople']} people, for {date} at {time}:\n\n"
            + "\n".join(lines) + "\n\nEnjoy your meal!")


def lambda_handler(event, context):
    msgs = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=10,
                               WaitTimeSeconds=1).get("Messages", [])
    for m in msgs:
        try:
            req = json.loads(m["Body"])
            restaurants = get_details(random_restaurant_ids(req["Cuisine"]))
            ses.send_email(
                Source=SENDER,
                Destination={"ToAddresses": [req["Email"]]},
                Message={
                    "Subject": {"Data": f"Your {req['Cuisine'].title()} restaurant suggestions"},
                    "Body": {"Text": {"Data": build_email(req, restaurants)}},
                },
            )
            sqs.delete_message(QueueUrl=QUEUE_URL,
                               ReceiptHandle=m["ReceiptHandle"])
            print("Sent suggestions to", req["Email"])
        except Exception as e:
            print("Failed on message:", m["Body"], e)
    return {"processed": len(msgs)}
