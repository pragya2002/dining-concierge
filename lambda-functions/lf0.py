import json
import os
import uuid
from datetime import datetime, timezone

import boto3


lex = boto3.client("lexv2-runtime")

BOT_ID = os.environ["LEX_BOT_ID"]
BOT_ALIAS_ID = os.environ["LEX_BOT_ALIAS_ID"]
LOCALE_ID = os.environ["LEX_LOCALE_ID"]


def lambda_handler(event, context):
    print("Received event:")
    print(json.dumps(event))

    # Get the messages array from the request defined by swagger.yaml
    messages = event.get("messages", [])

    if not messages:
        return {
            "messages": [
                {
                    "type": "unstructured",
                    "unstructured": {
                        "id": str(uuid.uuid4()),
                        "text": "No message was provided.",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            ]
        }

    # Get the user's text from the first message
    user_message = messages[0]["unstructured"]["text"]

    # Keep the same conversation/session alive in Lex.
    # If the frontend supplied an id, use it as the Lex session id.
    session_id = (
        messages[0]["unstructured"].get("id")
        or str(uuid.uuid4())
    )

    # Send the user's text to Amazon Lex
    lex_response = lex.recognize_text(
        botId=BOT_ID,
        botAliasId=BOT_ALIAS_ID,
        localeId=LOCALE_ID,
        sessionId=session_id,
        text=user_message
    )

    # Get Lex's text response
    lex_messages = lex_response.get("messages", [])

    if lex_messages:
        response_text = lex_messages[0].get(
            "content",
            "I couldn't understand that."
        )
    else:
        response_text = "I couldn't understand that."

    # Return the format required by swagger.yaml
    return {
        "messages": [
            {
                "type": "unstructured",
                "unstructured": {
                    "id": session_id,
                    "text": response_text,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        ]
    }