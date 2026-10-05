import json
import os
import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]

VALID_CUISINES = {
    "chinese",
    "italian",
    "indian",
    "japanese",
    "mexican"
}


def get_slot_value(slots, slot_name):
    slot = slots.get(slot_name)

    if slot and slot.get("value"):
        return slot["value"].get("interpretedValue")

    return None


def elicit_slot(intent, slot_name, message):
    return {
        "sessionState": {
            "dialogAction": {
                "type": "ElicitSlot",
                "slotToElicit": slot_name
            },
            "intent": intent
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": message
            }
        ]
    }


def delegate(intent):
    return {
        "sessionState": {
            "dialogAction": {
                "type": "Delegate"
            },
            "intent": intent
        }
    }


def close_intent(intent_name, message):
    return {
        "sessionState": {
            "dialogAction": {
                "type": "Close"
            },
            "intent": {
                "name": intent_name,
                "state": "Fulfilled"
            }
        },
        "messages": [
            {
                "contentType": "PlainText",
                "content": message
            }
        ]
    }


def lambda_handler(event, context):
    print("Received event:")
    print(json.dumps(event))

    intent = event["sessionState"]["intent"]
    intent_name = intent["name"]

    # GreetingIntent
    if intent_name == "GreetingIntent":
        return close_intent(
            intent_name,
            "Hi! How can I help you today?"
        )

    # ThankYouIntent
    if intent_name == "ThankYouIntent":
        return close_intent(
            intent_name,
            "You're welcome! Have a great day!"
        )

    # DiningSuggestionsIntent
    if intent_name == "DiningSuggestionsIntent":
        slots = intent.get("slots") or {}

        location = get_slot_value(slots, "Location")
        cuisine = get_slot_value(slots, "Cuisine")

        # Validate location
        if location and location.lower() not in {
            "manhattan",
            "new york",
            "new york city",
            "nyc"
        }:
            slots["Location"] = None

            return elicit_slot(
                intent,
                "Location",
                "Sorry, I can only provide restaurant suggestions for Manhattan. Please enter Manhattan as your location."
            )

        # Validate cuisine
        if cuisine and cuisine.lower() not in VALID_CUISINES:
            slots["Cuisine"] = None

            return elicit_slot(
                intent,
                "Cuisine",
                "Sorry, I currently support Chinese, Italian, Indian, Japanese, and Mexican cuisine. Which one would you like?"
            )

        # Lex is still collecting slots
        invocation_source = event.get("invocationSource")

        if invocation_source == "DialogCodeHook":
            return delegate(intent)

        # All slots have been collected, so fulfillment begins
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

        return close_intent(
            intent_name,
            "You're all set! I will send restaurant recommendations to your email shortly."
        )

    # Safety fallback
    return close_intent(
        intent_name,
        "Sorry, I couldn't process that request."
    )