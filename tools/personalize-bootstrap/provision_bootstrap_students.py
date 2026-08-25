#!/usr/bin/env python3
"""
provision_bootstrap_students.py

Creates REAL Cognito accounts and REAL DynamoDB ENROL# records for 30
bootstrap students, so Personalize training uses actual platform identities
-- not fabricated string IDs. Engagement HISTORY is still synthetic (no one
has genuinely used the platform yet); the IDENTITIES are real accounts this
tooling creates and owns, same category as the manually-created
test-student-N accounts used elsewhere in this project, just clearly
namespaced apart from them.

Naming convention: bootstrap-{cohort}-{NNN}@{domain}, e.g.
bootstrap-friction-000@campusiq.dev -- unmistakably distinct from
test-student-N@... accounts, which represent real validated evidence and
should never be confused with these throwaway ones.

Writes bootstrap_students.json (sub + username per cohort) for
generate_bootstrap_dataset.py to read next.

Run teardown_bootstrap_students.py once validation evidence is captured --
left alone, these 30 accounts will inflate enrolled_count on
GET /teacher/me/courses going forward.

REQUIRED environment variables:
    COGNITO_USER_POOL_ID
    DYNAMODB_TABLE_NAME
Optional:
    AWS_REGION              (default: us-east-1)
    COURSE_ID                (default: phys101)
    BOOTSTRAP_EMAIL_DOMAIN    (default: campusiq.dev)
    BOOTSTRAP_PASSWORD        (default: a fixed dev-only password --
                               only acceptable because these accounts are
                               deleted by teardown_bootstrap_students.py
                               once evidence is captured, never left running)
"""

import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
COURSE_ID = os.environ.get("COURSE_ID", "phys101")
EMAIL_DOMAIN = os.environ.get("BOOTSTRAP_EMAIL_DOMAIN", "campusiq.dev")
PASSWORD = os.environ.get("BOOTSTRAP_PASSWORD", "Bootstrap@Temp123!")

STUDENTS_PER_COHORT = 10
COHORTS = ["friction", "inertia", "balanced"]

cognito = boto3.client("cognito-idp", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def create_student(username: str) -> str:
    """Creates a Cognito user, sets a permanent password, adds to STUDENT group. Returns the real sub."""
    try:
        cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=username,
            TemporaryPassword=PASSWORD,
            UserAttributes=[
                {"Name": "email", "Value": username},
                {"Name": "email_verified", "Value": "true"},
            ],
        )
    except cognito.exceptions.UsernameExistsException:
        print(f"  {username} already exists, reusing.")

    cognito.admin_set_user_password(UserPoolId=USER_POOL_ID, Username=username, Password=PASSWORD, Permanent=True)

    try:
        cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=username, GroupName="STUDENT")
    except cognito.exceptions.ClientError as e:
        if "already" not in str(e).lower():
            raise

    user = cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=username)
    return next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")


def enroll_student(sub: str):
    """Same ENROL# shape used for the real test-student accounts elsewhere in this project."""
    table.put_item(Item={
        "PK": f"STUDENT#{sub}",
        "SK": f"ENROL#{COURSE_ID}",
        "entity_type": "ENROLMENT",
        "student_id": sub,
        "course_id": COURSE_ID,
        "status": "active",
        "enrolled_at": "2026-08-10T00:00:00Z",
        "GSI1_PK": f"COURSE#{COURSE_ID}",
        "GSI1_SK": f"STUDENT#{sub}",
    })


def main():
    roster = {}

    for cohort in COHORTS:
        roster[cohort] = []
        for i in range(STUDENTS_PER_COHORT):
            username = f"bootstrap-{cohort}-{i:03d}@{EMAIL_DOMAIN}"
            print(f"Provisioning {username}...")
            sub = create_student(username)
            enroll_student(sub)
            roster[cohort].append({"username": username, "sub": sub})

    with open("bootstrap_students.json", "w") as f:
        json.dump(roster, f, indent=2)

    total = sum(len(v) for v in roster.values())
    print(f"\nProvisioned and enrolled {total} bootstrap students across {len(COHORTS)} cohorts in {COURSE_ID}.")
    print("Wrote bootstrap_students.json -- generate_bootstrap_dataset.py reads this next.")
    print("\nRemember: run teardown_bootstrap_students.py after capturing validation evidence, "
          "or these accounts will inflate enrolled_count on GET /teacher/me/courses.")


if __name__ == "__main__":
    main()
