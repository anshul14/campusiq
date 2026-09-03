# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


# infrastructure/cdk/stacks/agent_stack.py
#
# Provisions CampusIQ's Bedrock Knowledge Base, backed by Amazon S3
# Vectors as the vector store — chosen over OpenSearch Serverless for
# its pay-per-use pricing with no idle-cost floor.
#
# Imports the content bucket ARN from StorageStack via Fn.import_value,
# the same cross-stack pattern used elsewhere for Cognito/content-bucket
# values, rather than a direct construct reference.
#
# Outputs the Knowledge Base ID and Data Source ID as CfnOutputs, for
# ComputeStack's ingestion Lambda to call bedrock-agent:StartIngestionJob.

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3vectors as s3vectors,
    aws_bedrock as bedrock,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct

# Titan Embed Text V2 — chosen for broad regional availability and no
# separate model-access request (unlike some Cohere/third-party
# embedding models on Bedrock). 1024 dimensions is that model's default.
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSION = 1024

# Fixed-size chunking. Course modules are prose-length, not short
# fragments, so a larger window than typical RAG demo defaults.
CHUNK_MAX_TOKENS = 500
CHUNK_OVERLAP_PERCENTAGE = 20


class AgentStack(Stack):
    """
    Provisions the Bedrock Knowledge Base for CampusIQ course content.

    Exposes:
        self.knowledge_base   — CfnKnowledgeBase construct
        self.data_source      — CfnDataSource construct
    """

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            deployment_name: str,
            config: dict,
            **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.deployment_name = deployment_name

        # ------------------------------------------------------------------
        # Cross-stack import — content bucket ARN from StorageStack.
        # Same Fn.import_value pattern compute_stack.py already uses for
        # this exact export (campusiq-{deployment}-content-bucket-arn).
        # ------------------------------------------------------------------
        content_bucket_arn = cdk.Fn.import_value(
            f"campusiq-{deployment_name}-content-bucket-arn"
        )

        # ------------------------------------------------------------------
        # S3 Vector Bucket + Index
        # No idle cost — pay-per-use, unlike OpenSearch Serverless's OCU
        # floor.
        # ------------------------------------------------------------------
        self.vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "VectorBucket",
            vector_bucket_name=f"campusiq-{deployment_name}-vectors",
        )

        self.vector_index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            index_name=f"campusiq-{deployment_name}-content-index",
            vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
            data_type="float32",
            dimension=EMBEDDING_DIMENSION,
            distance_metric="cosine",
            # S3 Vectors treats every metadata key as filterable by
            # default, capped at 2KB total. Bedrock KB automatically
            # attaches the chunk's own text as AMAZON_BEDROCK_TEXT and
            # document metadata as AMAZON_BEDROCK_METADATA — any chunk
            # of real content exceeds 2KB on the text field alone, so
            # both must be declared non-filterable (40KB cap instead) or
            # ingestion fails on nearly every document.
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=[
                    "AMAZON_BEDROCK_TEXT",
                    "AMAZON_BEDROCK_METADATA",
                ],
            ),
        )

        # ------------------------------------------------------------------
        # IAM role for the Knowledge Base
        # Scoped narrowly: assumable only by Bedrock, only for a KB in
        # this account, only for this specific embedding model, content
        # bucket, and vector index — not wildcarded to "any KB" or "any
        # bucket".
        # ------------------------------------------------------------------
        embedding_model_arn = f"arn:aws:bedrock:{self.region}::foundation-model/{EMBEDDING_MODEL_ID}"

        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            role_name=f"campusiq-{deployment_name}-kb-role",
            assumed_by=iam.PrincipalWithConditions(
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    },
                },
            ),
        )

        kb_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[embedding_model_arn],
            )
        )

        # Content bucket read — whole bucket, matching the data source's
        # scope below (no inclusion_prefixes; see that resource's comment
        # for why the original three-domain-prefix scoping doesn't work).
        # IAM here has to match what the data source can actually reach,
        # not be narrower than it for no reason.
        kb_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:ListBucket"],
                resources=[content_bucket_arn],
            )
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[f"{content_bucket_arn}/*"],
            )
        )

        kb_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:GetIndex",
                ],
                resources=[self.vector_index.attr_index_arn],
            )
        )

        # ------------------------------------------------------------------
        # Knowledge Base
        # ------------------------------------------------------------------
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"campusiq-{deployment_name}-kb",
            description="CampusIQ course content — grounds Tutor Agent RAG responses",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn,
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=self.vector_index.attr_index_arn,
                    vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
                ),
            ),
        )
        # Avoids a permission race on first deploy — the KB tries to
        # validate the role can do what it claims before the role's
        # policies have necessarily propagated otherwise.
        self.knowledge_base.node.add_dependency(kb_role)

        # ------------------------------------------------------------------
        # Data Source — points the KB at the existing content bucket.
        #
        # RETAIN on data_deletion_policy, not DELETE: matches the RETAIN
        # posture already used on the DynamoDB table and content bucket
        # for anything holding real data, and avoids a CloudFormation
        # failure mode where a stack can't be destroyed cleanly if a data
        # source's indexed vectors aren't emptied first.
        #
        # No inclusion_prefixes — CloudFormation allows only one prefix
        # per data source, which rules out scoping to the three DomainEnum
        # prefixes (university/, k12/, corporate/) individually. Whole-
        # bucket scan is the correct fallback: raw-uploads/ content is
        # binary/video, which Bedrock's ingestion can't parse as a
        # document and skips rather than errors on.
        #
        # Ingestion is triggered per-module by a ModulePublished event,
        # not a deploy-time bulk sync — no sync-on-deploy custom resource
        # here.
        # ------------------------------------------------------------------
        self.data_source = bedrock.CfnDataSource(
            self,
            "ContentDataSource",
            name=f"campusiq-{deployment_name}-content-source",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            data_deletion_policy="RETAIN",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=content_bucket_arn,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=CHUNK_MAX_TOKENS,
                        overlap_percentage=CHUNK_OVERLAP_PERCENTAGE,
                    ),
                ),
            ),
        )
        self.data_source.add_dependency(self.knowledge_base)

        # ------------------------------------------------------------------
        # CloudFormation outputs — consumed by ComputeStack's ingestion
        # Lambda to call bedrock-agent:StartIngestionJob.
        # ------------------------------------------------------------------
        CfnOutput(
            self,
            "KnowledgeBaseId",
            value=self.knowledge_base.attr_knowledge_base_id,
            export_name=f"campusiq-{deployment_name}-kb-id",
            description="Bedrock Knowledge Base ID — needed for StartIngestionJob and the Tutor Agent's RAG config",
        )

        CfnOutput(
            self,
            "DataSourceId",
            value=self.data_source.attr_data_source_id,
            export_name=f"campusiq-{deployment_name}-kb-data-source-id",
            description="Bedrock KB Data Source ID — needed for StartIngestionJob",
        )

        CfnOutput(
            self,
            "VectorBucketArn",
            value=self.vector_bucket.attr_vector_bucket_arn,
            export_name=f"campusiq-{deployment_name}-vector-bucket-arn",
        )

        CfnOutput(
            self,
            "VectorIndexArn",
            value=self.vector_index.attr_index_arn,
            export_name=f"campusiq-{deployment_name}-vector-index-arn",
        )