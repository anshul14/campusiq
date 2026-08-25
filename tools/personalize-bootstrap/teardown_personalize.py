#!/usr/bin/env python3
"""
teardown_personalize.py

Deletes everything provision_and_validate_personalize.py created, in the
order Personalize requires (solutions before dataset group; dataset group
before its datasets can be considered gone; schemas after datasets).

Run this AFTER you've saved the batch inference output / screenshots as
evidence -- once this runs, the trained model is gone and would need
retraining from scratch (or against real usage data, later).
"""

import time

import boto3

REGION = "us-east-1"
DATASET_GROUP_NAME = "campusiq-bootstrap-dg"
SOLUTION_NAME = "campusiq-bootstrap-solution"
ROLE_NAME = "CampusIQPersonalizeBootstrapRole"

sts = boto3.client("sts", region_name=REGION)
ACCOUNT_ID = sts.get_caller_identity()["Account"]
BUCKET_NAME = f"campusiq-personalize-bootstrap-{ACCOUNT_ID}"

personalize = boto3.client("personalize", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)


def find_dataset_group_arn():
    for dg in personalize.list_dataset_groups()["datasetGroups"]:
        if dg["name"] == DATASET_GROUP_NAME:
            return dg["datasetGroupArn"]
    return None


def find_solution_arn(dataset_group_arn):
    for s in personalize.list_solutions(datasetGroupArn=dataset_group_arn)["solutions"]:
        if s["name"] == SOLUTION_NAME:
            return s["solutionArn"]
    return None


def confirm():
    print(f"This will PERMANENTLY DELETE the following, if they exist:")
    print(f"  - Personalize dataset group: {DATASET_GROUP_NAME} (and its solution, datasets, schemas)")
    print(f"  - S3 bucket: {BUCKET_NAME} (and all its contents)")
    print(f"  - IAM role: {ROLE_NAME}")
    print()
    response = input(f"Type the dataset group name ({DATASET_GROUP_NAME}) to confirm: ")
    if response.strip() != DATASET_GROUP_NAME:
        print("Confirmation did not match — aborting, nothing was deleted.")
        raise SystemExit(1)


def main():
    confirm()

    dataset_group_arn = find_dataset_group_arn()
    if not dataset_group_arn:
        print("Dataset group not found — nothing to tear down (already deleted?).")
        return

    solution_arn = find_solution_arn(dataset_group_arn)
    if solution_arn:
        print(f"Deleting solution {SOLUTION_NAME}...")
        personalize.delete_solution(solutionArn=solution_arn)
        print("Waiting for solution deletion to complete (this is asynchronous)...")
        while True:
            try:
                personalize.describe_solution(solutionArn=solution_arn)
                time.sleep(15)
            except personalize.exceptions.ResourceNotFoundException:
                print("Solution deleted.")
                break

    print("Deleting datasets...")
    datasets = personalize.list_datasets(datasetGroupArn=dataset_group_arn)["datasets"]
    dataset_arns = [ds["datasetArn"] for ds in datasets]
    for ds in datasets:
        print(f"  Deleting dataset {ds['name']}...")
        personalize.delete_dataset(datasetArn=ds["datasetArn"])

    if dataset_arns:
        print("Waiting for dataset deletions to complete (this is asynchronous)...")
        for arn in dataset_arns:
            while True:
                try:
                    personalize.describe_dataset(datasetArn=arn)
                    time.sleep(15)
                except personalize.exceptions.ResourceNotFoundException:
                    break
        print("All datasets deleted.")

    print("Deleting schemas...")
    for schema in personalize.list_schemas()["schemas"]:
        if schema["name"].startswith("campusiq-bootstrap"):
            print(f"  Deleting schema {schema['name']}...")
            try:
                personalize.delete_schema(schemaArn=schema["schemaArn"])
            except personalize.exceptions.ResourceInUseException:
                print(f"  {schema['name']} still in use (datasets may not have finished deleting) — rerun this script in a few minutes.")

    print(f"Deleting dataset group {DATASET_GROUP_NAME}...")
    personalize.delete_dataset_group(datasetGroupArn=dataset_group_arn)

    print(f"Emptying and deleting S3 bucket {BUCKET_NAME}...")
    objects = s3.list_objects_v2(Bucket=BUCKET_NAME).get("Contents", [])
    if objects:
        s3.delete_objects(Bucket=BUCKET_NAME, Delete={"Objects": [{"Key": o["Key"]} for o in objects]})
    s3.delete_bucket(Bucket=BUCKET_NAME)

    print(f"Deleting inline policy and IAM role {ROLE_NAME}...")
    iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName="PersonalizeBootstrapS3Access")
    iam.delete_role(RoleName=ROLE_NAME)

    print("\nTeardown complete. No Personalize/S3/IAM resources from this "
          "bootstrap run should remain. Verify with:\n"
          "  aws personalize list-dataset-groups\n"
          "  aws s3 ls | grep campusiq-personalize-bootstrap\n"
          "  aws iam get-role --role-name CampusIQPersonalizeBootstrapRole  (should error, not found)")


if __name__ == "__main__":
    main()