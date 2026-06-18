#!/usr/bin/env python3
# infrastructure/cdk/app.py
#
# CDK entry point for CampusIQ.
# Reads campusiq.config.json from the repo root and wires all stacks.
#
# Usage:
#   cd infrastructure/cdk
#   cdk deploy --all

import json
import os
import aws_cdk as cdk
from stacks.database_stack import DatabaseStack

# ------------------------------------------------------------------
# Load campusiq.config.json from repo root
# campusiq.config.json is gitignored — never committed to source control
# campusiq.config.example.json is the template shipped in the repo
# ------------------------------------------------------------------
config_path = os.path.join(
    os.path.dirname(__file__),   # infrastructure/cdk/
    "..", "..",                  # repo root
    "campusiq.config.json",
)

with open(config_path) as f:
    config = json.load(f)

deployment  = config["deployment"]
institution = deployment["name"]        # e.g. "mit", "your-institution"
environment = deployment["environment"] # e.g. "dev", "staging", "prod"
aws_region  = deployment["region"]      # e.g. "us-east-1"
aws_account = deployment["account"]     # e.g. "123456789012"

# Stack name prefix — e.g. "CampusIQ-mit-dev"
stack_prefix = f"CampusIQ-{institution}-{environment}"

# ------------------------------------------------------------------
# CDK App
# ------------------------------------------------------------------
app = cdk.App()

env = cdk.Environment(account=aws_account, region=aws_region)

# ------------------------------------------------------------------
# Stack 1 — Database
# Must be deployed first — all other stacks depend on table name + ARN
# ------------------------------------------------------------------
database_stack = DatabaseStack(
    app,
    f"{stack_prefix}-Database",
    deployment_name=f"{institution}-{environment}",  # e.g. "mit-dev"
    env=env,
    description=f"CampusIQ {institution} {environment} — DynamoDB single table with 3 GSIs and Streams",
)

# ------------------------------------------------------------------
# Stack 2 — Compute (Lambdas + API Gateway)
# Uncommented once compute_stack.py is built
# ------------------------------------------------------------------
# from stacks.compute_stack import ComputeStack
# compute_stack = ComputeStack(
#     app,
#     f"{stack_prefix}-Compute",
#     deployment_name=f"{institution}-{environment}",
#     table=database_stack.table,
#     config=config,
#     env=env,
#     description=f"CampusIQ {institution} {environment} — Lambda functions and API Gateway",
# )
# compute_stack.add_dependency(database_stack)

app.synth()