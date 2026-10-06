import json
import os
import boto3
import requests
from dotenv import load_dotenv

load_dotenv()
HOST = os.environ["OS_HOST"]
AUTH = (os.environ["OS_USER"], os.environ["OS_PASS"])
table = boto3.resource(
    "dynamodb", region_name="us-east-1").Table("yelp-restaurants")

# 1. Create the index
requests.put(f"{HOST}/restaurants", auth=AUTH, json={
    "mappings": {"properties": {
        "RestaurantID": {"type": "keyword"},
        "Cuisine": {"type": "text"},
        "type": {"type": "keyword"}
    }}
})

# 2. Read all restaurants from DynamoDB
items, kwargs = [], {}
while True:
    resp = table.scan(ProjectionExpression="BusinessID, Cuisine", **kwargs)
    items += resp["Items"]
    if "LastEvaluatedKey" not in resp:
        break
    kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

# 3. Bulk upload to OpenSearch
lines = []
for it in items:
    lines.append(json.dumps(
        {"index": {"_index": "restaurants", "_id": it["BusinessID"]}}))
    lines.append(json.dumps(
        {"RestaurantID": it["BusinessID"], "Cuisine": it["Cuisine"], "type": "Restaurant"}))

r = requests.post(f"{HOST}/_bulk", auth=AUTH, data="\n".join(lines) + "\n",
                  headers={"Content-Type": "application/x-ndjson"})

# 4. Report
print(len(items), "indexed, errors:", r.json()["errors"])
