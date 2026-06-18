# infrastructure/cdk/stacks/database_stack.py
#
# Provisions the CampusIQ main DynamoDB table.
# Single table design — all 12 entity types in one table.
# Three GSIs + Streams enabled for the Cognitive Loop.
#
# Outputs table name and ARN as CfnOutput — consumed by compute_stack.py

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class DatabaseStack(Stack):
    """
    Provisions the CampusIQ main DynamoDB table.

    Exposes:
        self.table — the DynamoDB Table construct
                     passed into ComputeStack so Lambdas can be granted access
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        deployment_name: str,       # from campusiq.config.json — e.g. "dev", "prod"
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # Main table
        # Name pattern: campusiq-{deployment}-table
        # PK + SK composite key — all entity types share this table
        # ------------------------------------------------------------------
        self.table = dynamodb.Table(
            self,
            "CampusIQTable",
            table_name=f"campusiq-{deployment_name}-table",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # on-demand — no capacity planning
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,  # Cognitive Loop trigger
            point_in_time_recovery=True,                         # production safety
            removal_policy=RemovalPolicy.RETAIN,                 # never destroy on cdk destroy
        )

        # ------------------------------------------------------------------
        # GSI 1 — EntityTypeIndex
        # Purpose: list all entities of a given type (all courses, all students)
        # PK: entity_type  (e.g. "COURSE", "STUDENT", "GAP")
        # SK: none — returns all records of that type
        # Used by: GET /courses, admin listing endpoints
        # ------------------------------------------------------------------
        self.table.add_global_secondary_index(
            index_name="EntityTypeIndex",
            partition_key=dynamodb.Attribute(
                name="entity_type",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ------------------------------------------------------------------
        # GSI 2 — GapSeverityIndex
        # Purpose: retrieve student's weakest concepts in severity order
        # PK: GSI2_PK  = "STUDENT#{cognitoSub}"
        # SK: GSI2_SK  = zero-padded severity string e.g. "0.600"
        # ScanIndexForward=False → highest severity first
        # Used by: Orchestrator Agent context enrichment before every tutor call
        # ------------------------------------------------------------------
        self.table.add_global_secondary_index(
            index_name="GapSeverityIndex",
            partition_key=dynamodb.Attribute(
                name="GSI2_PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="GSI2_SK",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ------------------------------------------------------------------
        # GSI 3 — AtRiskIndex
        # Purpose: identify all at-risk students in a course (severity >= 0.700)
        # PK: GSI3_PK  = "COURSE#{courseId}"
        # SK: GSI3_SK  = zero-padded severity string e.g. "0.750"
        # Query: GSI3_PK = COURSE#{id}, GSI3_SK >= "0.700"
        # Used by: faculty alert Lambda → TeacherAlert records → EventBridge
        # ------------------------------------------------------------------
        self.table.add_global_secondary_index(
            index_name="AtRiskIndex",
            partition_key=dynamodb.Attribute(
                name="GSI3_PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="GSI3_SK",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ------------------------------------------------------------------
        # CloudFormation outputs
        # Consumed by compute_stack.py to wire Lambda env vars
        # ------------------------------------------------------------------
        CfnOutput(
            self,
            "TableName",
            value=self.table.table_name,
            export_name=f"campusiq-{deployment_name}-table-name",
            description="CampusIQ main DynamoDB table name",
        )

        CfnOutput(
            self,
            "TableArn",
            value=self.table.table_arn,
            export_name=f"campusiq-{deployment_name}-table-arn",
            description="CampusIQ main DynamoDB table ARN",
        )

        CfnOutput(
            self,
            "TableStreamArn",
            value=self.table.table_stream_arn,
            export_name=f"campusiq-{deployment_name}-table-stream-arn",
            description="CampusIQ DynamoDB Stream ARN — consumed by stream processor Lambda",
        )