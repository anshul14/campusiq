#!/usr/bin/env python3
"""
provision_and_validate_personalize.py

Provisions Amazon Personalize against the synthetic bootstrap dataset,
trains a solution, and validates it via a BATCH INFERENCE JOB rather than a
real-time campaign -- per the standing cost rule, this avoids ever creating
anything with hourly billing. Only one-time training compute and negligible
S3 storage are incurred, both cleaned up by teardown_personalize.py after
evidence is captured.

Run this AFTER generate_bootstrap_dataset.py has produced interactions.csv
and items.csv in the same directory.

PREREQUISITES (fill in below):
  - AWS credentials configured (same account/region as the rest of CampusIQ)
  - An S3 bucket you're fine using for this -- script creates one if it
    doesn't exist, named campusiq-personalize-bootstrap-<account-id>

This is a long-running script -- training alone can take 30-60+ minutes for
even a small dataset. It polls and prints status; safe to Ctrl+C and rerun,
each step checks whether its resource already exists before creating again.
"""

import json
import time
import boto3

REGION = "us-east-1"
DATASET_GROUP_NAME = "campusiq-bootstrap-dg"
SOLUTION_NAME = "campusiq-bootstrap-solution"
RECIPE_ARN = "arn:aws:personalize:::recipe/aws-user-personalization-v2"
ROLE_NAME = "CampusIQPersonalizeBootstrapRole"

sts = boto3.client("sts", region_name=REGION)
ACCOUNT_ID = sts.get_caller_identity()["Account"]
BUCKET_NAME = f"campusiq-personalize-bootstrap-{ACCOUNT_ID}"

s3 = boto3.client("s3", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
personalize = boto3.client("personalize", region_name=REGION)


def ensure_bucket():
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket {BUCKET_NAME} already exists.")
    except s3.exceptions.ClientError:
        print(f"Creating bucket {BUCKET_NAME}...")
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3.create_bucket(Bucket=BUCKET_NAME, CreateBucketConfiguration={"LocationConstraint": REGION})
        # Personalize requires the bucket to allow its service principal to read
        s3.put_bucket_policy(Bucket=BUCKET_NAME, Policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "PersonalizeRead",
                "Effect": "Allow",
                "Principal": {"Service": "personalize.amazonaws.com"},
                "Action": ["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
                "Resource": [f"arn:aws:s3:::{BUCKET_NAME}", f"arn:aws:s3:::{BUCKET_NAME}/*"],
            }],
        }))


def upload_data():
    print("Uploading interactions.csv and items.csv...")
    s3.upload_file("interactions.csv", BUCKET_NAME, "interactions.csv")
    s3.upload_file("items.csv", BUCKET_NAME, "items.csv")


def ensure_iam_role() -> str:
    """
    This is the role Personalize ASSUMES to read/write S3 during import jobs
    and batch inference -- it needs S3 access to one bucket, not broad
    Personalize API access. (An earlier draft of this script attached
    AmazonPersonalizeFullAccess here, which was the wrong kind of broad --
    that policy grants Personalize API calls, not S3 data access, and isn't
    what this role is for. Fixed to a scoped inline policy instead.)
    """
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "personalize.amazonaws.com"}, "Action": "sts:AssumeRole"}],
    }
    s3_access_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            "Resource": [f"arn:aws:s3:::{BUCKET_NAME}", f"arn:aws:s3:::{BUCKET_NAME}/*"],
        }],
    }
    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        print(f"IAM role {ROLE_NAME} already exists.")
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating IAM role {ROLE_NAME} (scoped to S3 access on {BUCKET_NAME} only)...")
        role = iam.create_role(RoleName=ROLE_NAME, AssumeRolePolicyDocument=json.dumps(trust_policy))
        iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="PersonalizeBootstrapS3Access", PolicyDocument=json.dumps(s3_access_policy))
        print("Waiting 15s for IAM role to propagate...")
        time.sleep(15)
    return role["Role"]["Arn"]


def ensure_schema(name: str, schema: dict) -> str:
    existing = personalize.list_schemas()["schemas"]
    for s in existing:
        if s["name"] == name:
            print(f"Schema {name} already exists.")
            return s["schemaArn"]
    print(f"Creating schema {name}...")
    return personalize.create_schema(name=name, schema=json.dumps(schema))["schemaArn"]


def ensure_dataset_group() -> str:
    existing = personalize.list_dataset_groups()["datasetGroups"]
    for dg in existing:
        if dg["name"] == DATASET_GROUP_NAME:
            print(f"Dataset group {DATASET_GROUP_NAME} already exists.")
            return dg["datasetGroupArn"]
    print(f"Creating dataset group {DATASET_GROUP_NAME}...")
    return personalize.create_dataset_group(name=DATASET_GROUP_NAME)["datasetGroupArn"]


def wait_for(describe_fn, arn_key: str, arn: str, active_status="ACTIVE", failed_status="CREATE FAILED", label=""):
    print(f"Waiting for {label} to become {active_status}...")
    while True:
        response = describe_fn(**{arn_key: arn})
        resource = list(response.values())[0]  # single sub-object, e.g. response["datasetGroup"]
        status_value = resource["status"]  # Personalize responses use lowercase "status", consistently
        print(f"  [{label}] status: {status_value}")
        if status_value == active_status:
            return
        if status_value == failed_status:
            raise RuntimeError(f"{label} failed: {response}")
        time.sleep(30)


def ensure_dataset(name: str, schema_arn: str, dataset_group_arn: str, dataset_type: str) -> str:
    """
    At most one dataset per type (INTERACTIONS/ITEMS/USERS) is allowed per
    dataset group -- matches the check-before-create pattern used by
    ensure_schema/ensure_dataset_group elsewhere in this script.
    """
    existing = personalize.list_datasets(datasetGroupArn=dataset_group_arn)["datasets"]
    for ds in existing:
        if ds["datasetType"] == dataset_type:
            print(f"{dataset_type} dataset already exists.")
            return ds["datasetArn"]
    print(f"Creating {dataset_type} dataset...")
    return personalize.create_dataset(
        name=name, schemaArn=schema_arn, datasetGroupArn=dataset_group_arn, datasetType=dataset_type,
    )["datasetArn"]


def ensure_solution(name: str, dataset_group_arn: str, recipe_arn: str) -> str:
    existing = personalize.list_solutions(datasetGroupArn=dataset_group_arn)["solutions"]
    for s in existing:
        if s["name"] == name:
            print(f"Solution {name} already exists.")
            return s["solutionArn"]
    print(f"Creating solution {name}...")
    return personalize.create_solution(name=name, datasetGroupArn=dataset_group_arn, recipeArn=recipe_arn)["solutionArn"]


def ensure_solution_version(solution_arn: str) -> str:
    """
    Reuses an existing ACTIVE (or already in-progress) solution version
    instead of unconditionally starting a new training job. Training costs
    real compute -- rerunning this script after fixing a downstream bug
    should never silently re-trigger a paid retrain of something that
    already succeeded.
    """
    existing = personalize.list_solution_versions(solutionArn=solution_arn)["solutionVersions"]
    for sv in existing:
        if sv["status"] == "ACTIVE":
            print("Reusing existing ACTIVE solution version -- skipping retraining.")
            return sv["solutionVersionArn"]
        if sv["status"] in ("CREATE PENDING", "CREATE IN_PROGRESS"):
            print("An in-progress solution version already exists -- will wait for it instead of starting a new one.")
            return sv["solutionVersionArn"]
    print("No usable solution version found -- starting training...")
    return personalize.create_solution_version(solutionArn=solution_arn)["solutionVersionArn"]


def ensure_batch_inference_job(job_name: str, solution_version_arn: str, input_path: str, output_path: str, role_arn: str) -> str:
    existing = personalize.list_batch_inference_jobs(solutionVersionArn=solution_version_arn)["batchInferenceJobs"]
    for job in existing:
        if job["jobName"] == job_name:
            print(f"Batch inference job {job_name} already exists.")
            return job["batchInferenceJobArn"]
    print("Starting batch inference job...")
    return personalize.create_batch_inference_job(
        jobName=job_name, solutionVersionArn=solution_version_arn,
        jobInput={"s3DataSource": {"path": input_path}},
        jobOutput={"s3DataDestination": {"path": output_path}},
        roleArn=role_arn, numResults=5,
    )["batchInferenceJobArn"]


def ensure_dataset_import_job(job_name: str, dataset_arn: str, s3_path: str, role_arn: str) -> str:
    existing = personalize.list_dataset_import_jobs(datasetArn=dataset_arn)["datasetImportJobs"]
    for job in existing:
        if job["jobName"] == job_name:
            print(f"Import job {job_name} already exists.")
            return job["datasetImportJobArn"]
    print(f"Starting {job_name}...")
    return personalize.create_dataset_import_job(
        jobName=job_name, datasetArn=dataset_arn,
        dataSource={"dataLocation": s3_path}, roleArn=role_arn,
    )["datasetImportJobArn"]


def main():
    ensure_bucket()
    upload_data()
    role_arn = ensure_iam_role()
    dataset_group_arn = ensure_dataset_group()
    wait_for(personalize.describe_dataset_group, "datasetGroupArn", dataset_group_arn, label="dataset group")

    interactions_schema = {
        "type": "record", "name": "Interactions", "namespace": "com.amazonaws.personalize.schema",
        "fields": [
            {"name": "USER_ID", "type": "string"},
            {"name": "ITEM_ID", "type": "string"},
            {"name": "TIMESTAMP", "type": "long"},
            {"name": "EVENT_TYPE", "type": "string"},
            {"name": "EVENT_VALUE", "type": "float"},
        ], "version": "1.0",
    }
    items_schema = {
        "type": "record", "name": "Items", "namespace": "com.amazonaws.personalize.schema",
        "fields": [
            {"name": "ITEM_ID", "type": "string"},
            {"name": "concept", "type": "string", "categorical": True},
            {"name": "difficulty", "type": "string", "categorical": True},
        ], "version": "1.0",
    }

    interactions_schema_arn = ensure_schema("campusiq-bootstrap-interactions-schema", interactions_schema)
    items_schema_arn = ensure_schema("campusiq-bootstrap-items-schema", items_schema)

    interactions_dataset_arn = ensure_dataset(
        "campusiq-bootstrap-interactions", interactions_schema_arn, dataset_group_arn, "INTERACTIONS")
    items_dataset_arn = ensure_dataset(
        "campusiq-bootstrap-items", items_schema_arn, dataset_group_arn, "ITEMS")

    interactions_import_arn = ensure_dataset_import_job(
        "campusiq-bootstrap-interactions-import", interactions_dataset_arn,
        f"s3://{BUCKET_NAME}/interactions.csv", role_arn)
    items_import_arn = ensure_dataset_import_job(
        "campusiq-bootstrap-items-import", items_dataset_arn,
        f"s3://{BUCKET_NAME}/items.csv", role_arn)

    wait_for(personalize.describe_dataset_import_job, "datasetImportJobArn", interactions_import_arn, label="interactions import")
    wait_for(personalize.describe_dataset_import_job, "datasetImportJobArn", items_import_arn, label="items import")

    solution_arn = ensure_solution(SOLUTION_NAME, dataset_group_arn, RECIPE_ARN)

    print("Checking for an existing solution version before starting training...")
    solution_version_arn = ensure_solution_version(solution_arn)
    wait_for(personalize.describe_solution_version, "solutionVersionArn", solution_version_arn, label="solution training")

    # ── Validation via batch inference — no real-time campaign created ──────
    # Two real students per cohort, read from the roster provision_bootstrap_students.py
    # wrote -- these are real Cognito subs, not fabricated IDs.
    with open("bootstrap_students.json") as f:
        roster = json.load(f)
    batch_input_entries = [
        (cohort, student["username"], student["sub"])
        for cohort, students in roster.items()
        for student in students[:2]
    ]
    batch_input = "\n".join(json.dumps({"userId": sub}) for _, _, sub in batch_input_entries)
    sub_to_label = {sub: f"{username} ({cohort})" for cohort, username, sub in batch_input_entries}
    with open("batch_input.json", "w") as f:
        f.write(batch_input)
    s3.upload_file("batch_input.json", BUCKET_NAME, "batch_input.json")

    batch_job_arn = ensure_batch_inference_job(
        "campusiq-bootstrap-validation", solution_version_arn,
        f"s3://{BUCKET_NAME}/batch_input.json", f"s3://{BUCKET_NAME}/batch_output/", role_arn,
    )

    wait_for(personalize.describe_batch_inference_job, "batchInferenceJobArn", batch_job_arn, label="batch inference")

    print("\nDownloading batch inference results...")
    s3.download_file(BUCKET_NAME, "batch_output/batch_input.json.out", "batch_output.json")

    print("\n=== VALIDATION RESULTS — recommendations per real bootstrap student ===\n")
    with open("batch_output.json") as f:
        for line in f:
            result = json.loads(line)
            sub = result["input"]["userId"]
            label = sub_to_label.get(sub, sub)
            recs = result["output"]["recommendedItems"]
            print(f"{label}: {recs}")

    print("\nExpected pattern: friction-cohort students should rank "
          "week3-friction-remediation near the top; inertia-cohort students should "
          "rank week3-inertia-remediation near the top; balanced-cohort students "
          "should show no strong single-item preference. Check the printed "
          "results above against this before treating training as validated.")

    print(f"\nSolution version ARN (save this): {solution_version_arn}")
    print("Once you've captured this output as evidence, run teardown_personalize.py "
          "to delete everything and avoid ongoing storage cost.")


if __name__ == "__main__":
    main()