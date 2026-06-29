# infrastructure/cdk/stacks/storage_stack.py
#
# Provisions the CampusIQ content storage layer:
#   - S3 content bucket — versioned, lifecycle managed
#   - CloudFront distribution — OAC access to S3
#
# S3 key structure:
#   {domain}/{courseId}/modules/{moduleId}/content.md   ← rich text
#   {domain}/{courseId}/modules/{moduleId}/content.pdf  ← PDF upload
#   {domain}/{courseId}/modules/{moduleId}/media/       ← HLS segments
#   {domain}/{courseId}/modules/{moduleId}/transcript.vtt ← Transcribe output
#   raw-uploads/{courseId}/{moduleId}/{filename}        ← MediaConvert input (temp)
#
# Exposes:
#   self.content_bucket      — S3 Bucket construct
#   self.distribution        — CloudFront Distribution construct
# Both passed into ComputeStack for Lambda env vars.

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class StorageStack(Stack):
    """
    Provisions CampusIQ content storage — S3 + CloudFront.

    Exposes:
        self.content_bucket  — S3 Bucket construct
        self.distribution    — CloudFront Distribution construct
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
        # S3 Content Bucket
        # Stores all course content — Markdown, PDFs, HLS video, transcripts.
        # Versioning enabled — teachers can restore previous content versions.
        # ------------------------------------------------------------------
        self.content_bucket = s3.Bucket(
            self,
            "ContentBucket",
            bucket_name=f"campusiq-{deployment_name}-content",

            # Versioning — every PUT creates a new version
            # Teachers can view and restore previous content versions
            versioned=True,

            # Encryption at rest — S3-managed keys (SSE-S3)
            # Upgrade to SSE-KMS for institutions with strict compliance requirements
            encryption=s3.BucketEncryption.S3_MANAGED,

            # Block all public access — content served via CloudFront only
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,

            # CORS — allows browser direct uploads via pre-signed URL
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],   # tighten to institution domain in prod
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],

            # Lifecycle rules
            lifecycle_rules=[
                # Content versions — keep last 10, expire after 90 days
                # Prevents unbounded storage growth from frequent edits
                s3.LifecycleRule(
                    id="ContentVersionExpiry",
                    noncurrent_version_expiration=Duration.days(90),
                    noncurrent_versions_to_retain=10,
                ),
                # Raw uploads prefix — temp MediaConvert input files
                # Auto-deleted after 7 days — MediaConvert output is in media/ prefix
                s3.LifecycleRule(
                    id="RawUploadExpiry",
                    prefix="raw-uploads/",
                    expiration=Duration.days(7),
                ),
                # Incomplete multipart uploads — clean up after 7 days
                s3.LifecycleRule(
                    id="AbortIncompleteMultipartUpload",
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
            ],

            # Retain on destroy — never accidentally delete course content
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------
        # CloudFront Distribution
        # Serves HLS video segments, PDFs, and static assets to students.
        # OAC (Origin Access Control) — CloudFront can read S3, browsers cannot.
        # ------------------------------------------------------------------

        # OAC — replaces deprecated OAI
        # Allows CloudFront to read from the private S3 bucket
        oac = cloudfront.S3OriginAccessControl(
            self,
            "ContentBucketOAC",
            description=f"OAC for CampusIQ {deployment_name} content bucket",
        )

        self.distribution = cloudfront.Distribution(
            self,
            "ContentDistribution",
            comment=f"CampusIQ {deployment_name} content CDN",

            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.content_bucket,
                    origin_access_control=oac,
                ),
                # Viewer protocol — HTTPS only
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,

                # Cache policy — optimised for content delivery
                # HLS segments are immutable once written so long TTL is safe
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,

                # Allowed methods — GET and HEAD only (read-only CDN)
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
            ),

            # Additional behaviour for HLS video — no-cache headers
            # HLS manifests (.m3u8) must not be cached — they change during live encoding
            additional_behaviors={
                "*/media/*.m3u8": cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(
                        self.content_bucket,
                        origin_access_control=oac,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                ),
            },

            # Price class — North America + Europe covers most institutions
            # Change to ALL for global deployments
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,

            # Error pages — return 404 for missing content rather than S3 XML error
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=404,
                    response_page_path="/404.html",
                    ttl=Duration.seconds(10),
                ),
            ],
        )

        # ------------------------------------------------------------------
        # Grant CloudFront OAC read access to the S3 bucket
        # Required for OAC — explicit bucket policy needed
        # ------------------------------------------------------------------
        self.content_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                actions=["s3:GetObject"],
                resources=[self.content_bucket.arn_for_objects("*")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/{self.distribution.distribution_id}"
                    }
                },
            )
        )

        # ------------------------------------------------------------------
        # CloudFormation outputs
        # ------------------------------------------------------------------
        CfnOutput(
            self,
            "ContentBucketName",
            value=self.content_bucket.bucket_name,
            export_name=f"campusiq-{deployment_name}-content-bucket",
            description="S3 content bucket name — used by content ingestion Lambdas",
        )

        CfnOutput(
            self,
            "ContentBucketArn",
            value=self.content_bucket.bucket_arn,
            export_name=f"campusiq-{deployment_name}-content-bucket-arn",
            description="S3 content bucket ARN — used for Lambda IAM grants",
        )

        CfnOutput(
            self,
            "CloudFrontDomainName",
            value=self.distribution.distribution_domain_name,
            export_name=f"campusiq-{deployment_name}-cloudfront-domain",
            description="CloudFront domain — set as NEXT_PUBLIC_CDN_URL in Next.js",
        )

        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            export_name=f"campusiq-{deployment_name}-cloudfront-id",
            description="CloudFront distribution ID — used for cache invalidation",
        )