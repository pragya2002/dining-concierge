import json
import os
import boto3

sqs = boto3.client("sqs")
QUEUE_URL = os.environ["QUEUE_URL"]

# Extra credit: table that remembers each user's last search
state_table = boto3.resource("dynamodb").Table(
    os.environ.get("STATE_TABLE", "user-search-state")
)

VALID_CUISINES = {
    "chinese",
    "italian",
    "indian",
    "japanese",
    "mexican"
}


VALID_LOCATIONS = {
    "manhattan",
    "new york",
    "new york city",
    "nyc"
}

YES_VALUES = {"yes", "yeah", "yep", "sure", "ok", "okay", "y"}


def normalize_location(location):
    """Treat every accepted spelling of Manhattan as the same location."""
    if location and location.lower() in VALID_LOCATIONS:
        return "manhattan"
    return (location or "").lower()


def get_last_search(user_id):
    """Return the user's last saved search from DynamoDB, or None."""
    if not user_id:
        return None
    try:
        return state_table.get_item(Key={"UserID": user_id}).get("Item")
    except Exception as e:
        print("Could not read search state:", e)
        return None


def get_slot_value(slots, slot_name):
    slot = slots.get(slot_name)

    if slot and slot.get("value"):
        return slot["value"].get("interpretedValue")

    return None


def elicit_slot(intent, slot_name, message):
    """
    Ask the user for a slot again.
    """
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
    """
    Tell Lex to continue collecting the remaining slots.
    """
    return {
        "sessionState": {
            "dialogAction": {
                "type": "Delegate"
            },
            "intent": intent
        }
    }


def close_intent(intent_name, message):
    """
    Finish an intent and return a message to the user.
    """
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

    # -------------------------------------------------
    # GreetingIntent
    # -------------------------------------------------
    if intent_name == "GreetingIntent":
        return close_intent(
            intent_name,
            "Hi! How can I help you today?"
        )

    # -------------------------------------------------
    # ThankYouIntent
    # -------------------------------------------------
    if intent_name == "ThankYouIntent":
        return close_intent(
            intent_name,
            "You're welcome! Have a great day!"
        )

    # -------------------------------------------------
    # FallbackIntent
    # -------------------------------------------------
    if intent_name == "FallbackIntent":
        return close_intent(
            intent_name,
            (
                "Sorry, I didn't understand that. "
                "I can help you find restaurant recommendations "
                "in Manhattan. You can say, "
                "\"I want restaurant recommendations.\""
            )
        )

    # -------------------------------------------------
    # DiningSuggestionsIntent
    # -------------------------------------------------
    if intent_name == "DiningSuggestionsIntent":

        slots = intent.get("slots") or {}

        location = get_slot_value(
            slots,
            "Location"
        )

        cuisine = get_slot_value(
            slots,
            "Cuisine"
        )

        number_of_people = get_slot_value(
            slots,
            "NumberOfPeople"
        )

        # ---------------------------------------------
        # Validate location
        # ---------------------------------------------
        if location and location.lower() not in VALID_LOCATIONS:
            slots["Location"] = None

            return elicit_slot(
                intent,
                "Location",
                (
                    "Sorry, I can only provide restaurant "
                    "suggestions for Manhattan. "
                    "Please enter Manhattan as your location."
                )
            )

        # ---------------------------------------------
        # Validate cuisine
        # ---------------------------------------------
        if cuisine and cuisine.lower() not in VALID_CUISINES:
            slots["Cuisine"] = None

            return elicit_slot(
                intent,
                "Cuisine",
                (
                    "Sorry, I currently support Chinese, "
                    "Italian, Indian, Japanese, and Mexican "
                    "cuisine. Which one would you like?"
                )
            )

        # ---------------------------------------------
        # Validate number of people
        # ---------------------------------------------
        if number_of_people:
            try:
                if int(number_of_people) <= 0:
                    slots["NumberOfPeople"] = None

                    return elicit_slot(
                        intent,
                        "NumberOfPeople",
                        (
                            "The number of people must be at "
                            "least 1. How many people are in "
                            "your party?"
                        )
                    )

            except ValueError:
                slots["NumberOfPeople"] = None

                return elicit_slot(
                    intent,
                    "NumberOfPeople",
                    (
                        "Please enter a valid number of people, "
                        "such as 2."
                    )
                )

        # ---------------------------------------------
        # Extra credit: same location and cuisine as
        # the user's last search? Offer to repeat it.
        # ---------------------------------------------
        user_id = event.get("sessionId")

        if location and cuisine:
            last = get_last_search(user_id)

            same_search = bool(
                last
                and normalize_location(last.get("Location"))
                == normalize_location(location)
                and last.get("Cuisine", "").lower() == cuisine.lower()
            )

            reuse_answer = get_slot_value(slots, "ReuseLast")

            if same_search and reuse_answer is None:
                return elicit_slot(
                    intent,
                    "ReuseLast",
                    (
                        f"Welcome back! Last time you also searched for "
                        f"{cuisine.title()} food in Manhattan. Would you "
                        f"like the same recommendations as last time? "
                        f"(yes/no)"
                    )
                )

            if (
                same_search
                and reuse_answer
                and reuse_answer.lower() in YES_VALUES
            ):
                repeat_request = dict(last.get("Request", {}))
                repeat_request.update({
                    "UserID": user_id,
                    "ReuseLast": True,
                    "Restaurants": last.get("Restaurants", [])
                })

                sqs.send_message(
                    QueueUrl=QUEUE_URL,
                    MessageBody=json.dumps(repeat_request, default=str)
                )

                return close_intent(
                    intent_name,
                    (
                        f"Great! I'll send the same "
                        f"{cuisine.title()} recommendations to "
                        f"{repeat_request.get('Email')} shortly."
                    )
                )

        # ---------------------------------------------
        # Dialog code hook:
        # Lex is still collecting information.
        # ---------------------------------------------
        invocation_source = event.get("invocationSource")

        if invocation_source == "DialogCodeHook":
            return delegate(intent)

        # ---------------------------------------------
        # Fulfillment:
        # All required slots have been collected.
        # ---------------------------------------------
        dining_request = {
            "Location": get_slot_value(
                slots,
                "Location"
            ),
            "Cuisine": get_slot_value(
                slots,
                "Cuisine"
            ),
            "DiningDate": get_slot_value(
                slots,
                "DiningDate"
            ),
            "DiningTime": get_slot_value(
                slots,
                "DiningTime"
            ),
            "NumberOfPeople": get_slot_value(
                slots,
                "NumberOfPeople"
            ),
            "Email": get_slot_value(
                slots,
                "Email"
            ),
            "UserID": event.get("sessionId")
        }

        # Send completed dining request to SQS Q1
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(dining_request)
        )

        return close_intent(
            intent_name,
            (
                "You're all set! I will send restaurant "
                "recommendations to your email shortly."
            )
        )

    # -------------------------------------------------
    # Safety fallback for any unexpected intent
    # -------------------------------------------------
    return close_intent(
        intent_name,
        (
            "Sorry, I couldn't process that request. "
            "Please try again."
        )
    )
