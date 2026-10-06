# Dining Concierge Chatbot

Cloud Computing and Big Data, Fall 2026, Assignment 1

**Team:** Aditya Jha (aj4955), Pragya Awasthi (pa2755)

A serverless, microservice driven web application that suggests restaurants through conversation. The user chats with a bot, which collects their dining preferences, and a few minutes later the user receives an email with restaurant suggestions.

## Architecture

```
S3 (frontend) → API Gateway → LF0 → Amazon Lex → LF1 → SQS (Q1)
                                                        ↓
                       EventBridge Scheduler (every minute) → LF2
                                                        ↓
                         OpenSearch (restaurant IDs by cuisine)
                                                        ↓
                         DynamoDB (restaurant details) → SES (email)
```

1. **Frontend** is a static site hosted on S3. It calls the chat API through the API Gateway generated SDK.
2. **API Gateway** exposes `POST /chatbot`, defined by `swagger/swagger.yaml`, with CORS enabled.
3. **LF0** receives the user's message, sends it to the Lex bot and returns the bot's reply.
4. **Amazon Lex (DiningConciergeBot)** handles three intents: `GreetingIntent`, `ThankYouIntent` and `DiningSuggestionsIntent`.
5. **LF1** is the Lex code hook. It validates location, cuisine and party size, then pushes the completed request to SQS queue **Q1**.
6. **LF2** is the queue worker, triggered every minute by EventBridge Scheduler. It reads requests from Q1, picks random restaurants for the requested cuisine from OpenSearch, fetches their details from DynamoDB and emails them through SES.

## Data

* **DynamoDB `yelp-restaurants`:** 1,020 unique Manhattan restaurants collected from the Yelp API across five cuisines (Chinese, Italian, Indian, Japanese, Mexican). Each item stores Business ID, Name, Address, Coordinates, Number of Reviews, Rating, Zip Code, Cuisine and `insertedAtTimestamp`.
* **OpenSearch index `restaurants`:** stores only `RestaurantID` and `Cuisine` for each restaurant (type `Restaurant`), used for fast random selection by cuisine.

## Extra credit: remembering the last search

* The frontend gives each browser a persistent user ID (stored in `localStorage`), which is used as the Lex session ID.
* After sending an email, LF2 saves the user's location, cuisine, request and recommended restaurants in the DynamoDB table **`user-search-state`**.
* When a returning user asks for the same location and cuisine, LF1 asks whether they want the same recommendations as last time. If they say yes, the saved restaurants are emailed again; if no, a fresh search runs.

## Repository structure

```
frontend/            Chat UI hosted on S3 (chat.html, assets, API Gateway SDK)
lambda-functions/    lf0.py (chat API), lf1.py (Lex code hook), lf2.py (queue worker)
other-scripts/       load_restaurants.py (Yelp → DynamoDB), load_opensearch.py (DynamoDB → OpenSearch)
swagger/             API specification
```

## Setup

1. Create the DynamoDB tables `yelp-restaurants` (partition key `BusinessID`) and `user-search-state` (partition key `UserID`).
2. Add `YELP_API_KEY` to a local `.env` file and run `python other-scripts/load_restaurants.py`.
3. Create the OpenSearch domain, add `OS_HOST`, `OS_USER` and `OS_PASS` to `.env`, then run `python other-scripts/load_opensearch.py`.
4. Create the SQS queue `Q1` and verify the sender and recipient email addresses in SES.
5. Deploy the Lambda functions with these environment variables:
   * **LF0:** `LEX_BOT_ID`, `LEX_BOT_ALIAS_ID`, `LEX_LOCALE_ID`
   * **LF1:** `QUEUE_URL`
   * **LF2:** `QUEUE_URL`, `OS_HOST`, `OS_USER`, `OS_PASS`, `SENDER_EMAIL`
6. Import `swagger/swagger.yaml` into API Gateway, connect it to LF0, enable CORS, deploy, and replace `frontend/assets/js/sdk/` with the generated SDK.
7. Create an EventBridge Scheduler rule that invokes LF2 every minute.
8. Upload the `frontend/` folder to the S3 bucket with static website hosting enabled.

Secrets (`.env`) are excluded from the repository through `.gitignore`.