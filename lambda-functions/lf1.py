import json
import os
import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]


def get_slot_value(slots, slot_name):
    slot = slots.get(slot_name)

    if slot and slot.get("value"):
        return slot["value"].get("interpretedValue")

    return None


def lambda_handler(event, context):
    print("Received event:")
    print(json.dumps(event))

    intent = event["sessionState"]["intent"]
    slots = intent["slots"]

    dining_request = {
        "Location": get_slot_value(slots, "Location"),
        "Cuisine": get_slot_value(slots, "Cuisine"),
        "DiningDate": get_slot_value(slots, "DiningDate"),
        "DiningTime": get_slot_value(slots, "DiningTime"),
        "NumberOfPeople": get_slot_value(slots, "NumberOfPeople"),
        "Email": get_slot_value(slots, "Email")
    }

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(dining_request)
    )

    return {
        "sessionState": {
            "dialogAction": {
                "type": "Close"
            },
            "intent": {
                "name": intent["name"],
                "state": "Fulfilled"
            }
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": "You're all set! I will send restaurant recommendations to your email shortly."
            }
        ]
    }