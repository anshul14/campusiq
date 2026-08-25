#!/usr/bin/env python3
"""
teardown_bootstrap_students.py

Deletes the Cognito accounts and DynamoDB ENROL# records created by
provision_bootstrap_students.py. Reads bootstrap_students.json to know
exactly which accounts to remove -- run this from the same directory
provisioning was run in, before that file gets cleaned up.

Requires typing "yes" to confirm before deleting anything.

REQUIRED environment variables:
    COGNITO_USER_POOL_ID
    DYNAMODB_TABLE_NAME
Optional:
    AWS_REGION    (default: us-east-1)
    COURSE_ID     (default: phys101)
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
COURSE_ID = os.environ.get("COURSE_ID", "phys101")

cognito = boto3.client("cognito-idp", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def main():
    if not os.path.exists("bootstrap_students.json"):
        print("bootstrap_students.json not found in this directory -- nothing to tear down, "
              "or run this from wherever provision_bootstrap_students.py was run.")
        return

    with open("bootstrap_students.json") as f:
        roster = json.load(f)

    total = sum(len(v) for v in roster.values())
    print(f"This will PERMANENTLY DELETE {total} Cognito accounts and their "
          f"ENROL#{COURSE_ID} DynamoDB records:")
    for cohort, students in roster.items():
        print(f"  {cohort}: {len(students)} accounts")

    response = input("\nType 'yes' to confirm: ")
    if response.strip().lower() != "yes":
        print("Aborting -- nothing was deleted.")
        return

    for cohort, students in roster.items():
        for entry in students:
            username, sub = entry["username"], entry["sub"]
            print(f"Deleting {username}...")
            try:
                cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=username)
            except cognito.exceptions.UserNotFoundException:
                print(f"  {username} already gone.")

            table.delete_item(Key={"PK": f"STUDENT#{sub}", "SK": f"ENROL#{COURSE_ID}"})

    os.remove("bootstrap_students.json")
    print(f"\nTeardown complete. {total} bootstrap accounts and their enrolment records "
          f"removed. enrolled_count on GET /teacher/me/courses should revert to its "
          f"pre-bootstrap value.")


if __name__ == "__main__":
    main()
