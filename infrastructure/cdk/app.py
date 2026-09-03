#!/usr/bin/env python3
# infrastructure/cdk/app.py

import json
import os
import aws_cdk as cdk
from stacks.database_stack import DatabaseStack
from stacks.auth_stack import AuthStack
from stacks.storage_stack import StorageStack
from stacks.agent_stack import AgentStack
from stacks.compute_stack import ComputeStack

config_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "campusiq.config.json",
)

with open(config_path) as f:
    config = json.load(f)

deployment    = config["deployment"]
institution   = deployment["name"]
environment   = deployment["environment"]
aws_region    = deployment["region"]
aws_account   = deployment["account"]

stack_prefix  = f"CampusIQ-{institution}-{environment}"

app = cdk.App()
env = cdk.Environment(account=aws_account, region=aws_region)

# Stack 1 — Database (no dependencies)
database_stack = DatabaseStack(
    app,
    f"{stack_prefix}-Database",
    deployment_name=f"{institution}-{environment}",
    env=env,
    description=f"CampusIQ {institution} {environment} — DynamoDB single table with 3 GSIs",
)

# Stack 2 — Auth (no dependencies)
auth_stack = AuthStack(
    app,
    f"{stack_prefix}-Auth",
    deployment_name=f"{institution}-{environment}",
    config=config,
    env=env,
    description=f"CampusIQ {institution} {environment} — Cognito User Pool with IdP federation",
)

# Stack 3 — Storage (no dependencies)
storage_stack = StorageStack(
    app,
    f"{stack_prefix}-Storage",
    deployment_name=f"{institution}-{environment}",
    config=config,
    env=env,
    description=f"CampusIQ {institution} {environment} — S3 content bucket and CloudFront",
)

# Stack 4 — Agent (depends on Storage for the content bucket export)
agent_stack = AgentStack(
    app,
    f"{stack_prefix}-Agent",
    deployment_name=f"{institution}-{environment}",
    config=config,
    env=env,
    description=f"CampusIQ {institution} {environment} — Bedrock Knowledge Base (S3 Vectors)",
)
agent_stack.add_dependency(storage_stack)

# Stack 5 — Compute (depends on all three foundational stacks)
compute_stack = ComputeStack(
    app,
    f"{stack_prefix}-Compute",
    deployment_name=f"{institution}-{environment}",
    table=database_stack.table,
    config=config,
    env=env,
    description=f"CampusIQ {institution} {environment} — Lambda functions and API Gateway",
)
compute_stack.add_dependency(database_stack)
compute_stack.add_dependency(auth_stack)
compute_stack.add_dependency(storage_stack)

app.synth()