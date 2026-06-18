# infrastructure/cdk/stacks/compute_stack.py
#
# Provisions all CampusIQ Lambda functions, API Gateway, and EventBridge.
# Depends on DatabaseStack — receives table as a construct reference.
#
# Lambda runtime model (canonical — see Master Reference v2 Section 5):
#   AgentCore runtime:  Orchestrator, Tutor Agent (conversational memory + KB RAG)
#   Lambda + InvokeModel: Gap Detection, Recommendation, Content Adaptation, Assessment
#   HTTP Lambdas:       Courses, Students, Tutor (thin wrapper), Quiz, Teacher, Admin
#   Event-driven:       Stream Processor, Gap Detection, Recommendation, Content Adaptation

import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda_event_sources as event_sources,
    aws_dynamodb as dynamodb,
    CfnOutput,
)
from constructs import Construct

# Absolute path to the repo root — used for Code.from_asset()
# infrastructure/cdk/stacks/compute_stack.py → up 3 levels = repo root
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class ComputeStack(Stack):
    """
    Provisions all CampusIQ compute resources.

    Receives:
        table           — DynamoDB Table construct from DatabaseStack
        deployment_name — e.g. "mit-dev"
        config          — full campusiq.config.json as dict
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        deployment_name: str,
        table: dynamodb.Table,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.table = table
        self.deployment_name = deployment_name
        self.config = config

        # ------------------------------------------------------------------
        # Shared environment variables — injected into every Lambda
        # ------------------------------------------------------------------
        self.shared_env = {
            "DYNAMODB_TABLE_NAME":      table.table_name,
            "ALLOWED_ORIGINS":          config["domain"].get("allowed_origins", "http://localhost:3000"),
            "POWERTOOLS_SERVICE_NAME":  f"campusiq-{deployment_name}",
            "LOG_LEVEL":                "DEBUG" if "dev" in deployment_name else "INFO",
            "DEPLOYMENT_NAME":          deployment_name,
        }

        # ------------------------------------------------------------------
        # EventBridge custom event bus — Cognitive Loop
        # ------------------------------------------------------------------
        self.event_bus = events.EventBus(
            self,
            "CampusIQEventBus",
            event_bus_name=f"campusiq-{deployment_name}-events",
        )

        CfnOutput(
            self,
            "EventBusName",
            value=self.event_bus.event_bus_name,
            export_name=f"campusiq-{deployment_name}-event-bus-name",
        )

        # ------------------------------------------------------------------
        # Build all Lambdas
        # ------------------------------------------------------------------
        self._build_http_lambdas()
        self._build_event_driven_lambdas()
        self._build_api_gateway()
        self._wire_eventbridge_rules()

    # ======================================================================
    # HTTP LAMBDAS — FastAPI + Mangum, one per route group
    # ======================================================================

    def _build_http_lambdas(self):

        # ------------------------------------------------------------------
        # Courses Lambda
        # Routes: GET/POST /courses, PATCH/DELETE /courses/{id},
        #         GET/POST /courses/{id}/modules, PATCH/DELETE /courses/{id}/modules/{id}
        #         POST /courses/{id}/enrolments
        # ------------------------------------------------------------------
        self.courses_lambda = self._http_lambda(
            name="Courses",
            entry="src/application/lambdas/courses",
            memory=512,
            timeout=29,
            extra_env={},
        )
        # DynamoDB read + write for course and module records
        self.table.grant_read_write_data(self.courses_lambda)

        # ------------------------------------------------------------------
        # Students Lambda
        # Routes: GET /students/me, GET /students/me/courses,
        #         PUT /students/me/courses/{id}/modules/{id}/progress
        # ------------------------------------------------------------------
        self.students_lambda = self._http_lambda(
            name="Students",
            entry="src/application/lambdas/students",
            memory=512,
            timeout=29,
            extra_env={},
        )
        self.table.grant_read_write_data(self.students_lambda)

        # ------------------------------------------------------------------
        # Tutor Lambda — thin AgentCore wrapper
        # Routes: POST /tutor/chat, GET /tutor/history
        # Memory 1024MB — Bedrock streaming needs headroom
        # Timeout 30s — AgentCore responses can be slow
        # ------------------------------------------------------------------
        self.tutor_lambda = self._http_lambda(
            name="Tutor",
            entry="src/application/lambdas/tutor",
            memory=1024,
            timeout=30,
            extra_env={
                "TUTOR_AGENT_ID":       self.node.try_get_context("tutor_agent_id") or "REPLACE_WITH_AGENT_ID",
                "TUTOR_AGENT_ALIAS_ID": self.node.try_get_context("tutor_agent_alias_id") or "REPLACE_WITH_ALIAS_ID",
            },
        )
        # DynamoDB read — conversation history lookup (Redis is primary store)
        self.table.grant_read_data(self.tutor_lambda)
        # Bedrock AgentCore invoke permission
        self.tutor_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeAgent"],
                resources=["*"],  # Scope to agent ARN once provisioned
            )
        )

        # ------------------------------------------------------------------
        # Quiz Lambda
        # Routes: POST /quiz/submit, GET /quiz/results,
        #         POST /quiz/generate (calls Assessment Lambda)
        # ------------------------------------------------------------------
        self.quiz_lambda = self._http_lambda(
            name="Quiz",
            entry="src/application/lambdas/quiz",
            memory=512,
            timeout=29,
            extra_env={},
        )
        self.table.grant_read_write_data(self.quiz_lambda)
        # Bedrock InvokeModel for Assessment Agent (quiz generation)
        self.quiz_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # ------------------------------------------------------------------
        # Teacher Lambda
        # Routes: GET /teacher/courses, GET /teacher/courses/{id}/students,
        #         GET /teacher/courses/{id}/gaps (faculty heatmap)
        # ------------------------------------------------------------------
        self.teacher_lambda = self._http_lambda(
            name="Teacher",
            entry="src/application/lambdas/teacher",
            memory=512,
            timeout=29,
            extra_env={},
        )
        self.table.grant_read_data(self.teacher_lambda)

        # ------------------------------------------------------------------
        # Admin Lambda
        # Routes: GET /admin/*, POST /admin/*, user management
        # ------------------------------------------------------------------
        self.admin_lambda = self._http_lambda(
            name="Admin",
            entry="src/application/lambdas/admin",
            memory=512,
            timeout=29,
            extra_env={},
        )
        self.table.grant_read_write_data(self.admin_lambda)

    # ======================================================================
    # EVENT-DRIVEN LAMBDAS — plain handler.py, no FastAPI
    # ======================================================================

    def _build_event_driven_lambdas(self):

        # ------------------------------------------------------------------
        # Stream Processor Lambda
        # Trigger: DynamoDB Streams (NEW_AND_OLD_IMAGES)
        # Purpose: Translate DynamoDB stream events → EventBridge events
        #          QuizCompleted on RESULT# write
        #          GapDetected on GAP# write when severity > 0.7
        # Memory: 256MB — lightweight translation, no ML
        # Timeout: 60s — batch processing of stream records
        # ------------------------------------------------------------------
        self.stream_processor_lambda = self._event_lambda(
            name="StreamProcessor",
            entry="src/application/lambdas/stream_processor",
            memory=256,
            timeout=60,
            extra_env={
                "EVENT_BUS_NAME": self.event_bus.event_bus_name,
            },
        )
        # DynamoDB Streams read
        self.table.grant_stream_read(self.stream_processor_lambda)
        # EventBridge put events
        self.event_bus.grant_put_events_to(self.stream_processor_lambda)
        # Wire DynamoDB Stream as event source
        self.stream_processor_lambda.add_event_source(
            event_sources.DynamoEventSource(
                self.table,
                starting_position=lambda_.StartingPosition.TRIM_HORIZON,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=3,
            )
        )

        # ------------------------------------------------------------------
        # Gap Detection Lambda
        # Trigger: EventBridge QuizCompleted event
        # Purpose: Calculate gap_severity per concept from quiz concept_scores
        #          Write/update GAP#{conceptId} records in DynamoDB
        #          Uses Bedrock InvokeModel (Claude 3.5 Sonnet) for analysis
        # Memory: 512MB — Bedrock InvokeModel call
        # Timeout: 60s — LLM call latency
        # ------------------------------------------------------------------
        self.gap_detection_lambda = self._event_lambda(
            name="GapDetection",
            entry="src/application/lambdas/gap_detection",
            memory=512,
            timeout=60,
            extra_env={},
        )
        self.table.grant_read_write_data(self.gap_detection_lambda)
        self.gap_detection_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # ------------------------------------------------------------------
        # Recommendation Lambda
        # Trigger: EventBridge GapDetected event
        # Purpose: Query Amazon Personalize with gap context
        #          Write updated LearningPath record to DynamoDB (24hr TTL)
        # Memory: 512MB
        # Timeout: 60s — Personalize API call
        # ------------------------------------------------------------------
        self.recommendation_lambda = self._event_lambda(
            name="Recommendation",
            entry="src/application/lambdas/recommendation",
            memory=512,
            timeout=60,
            extra_env={
                "PERSONALIZE_CAMPAIGN_ARN": self.node.try_get_context("personalize_campaign_arn") or "REPLACE_WITH_CAMPAIGN_ARN",
            },
        )
        self.table.grant_read_write_data(self.recommendation_lambda)
        self.recommendation_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["personalize:GetRecommendations"],
                resources=["*"],
            )
        )

        # ------------------------------------------------------------------
        # Content Adaptation Lambda
        # Trigger: EventBridge GapDetected event (severity > 0.85 only)
        # Purpose: Rewrite module Markdown content at lower difficulty
        #          Uses Bedrock InvokeModel (Claude 3 Haiku — cheaper for rewriting)
        #          Saves adapted variant to S3, updates module record
        # Memory: 512MB
        # Timeout: 90s — content rewriting is slower than analysis
        # ------------------------------------------------------------------
        self.content_adaptation_lambda = self._event_lambda(
            name="ContentAdaptation",
            entry="src/application/lambdas/content_adaptation",
            memory=512,
            timeout=90,
            extra_env={
                "CONTENT_BUCKET_NAME": self.node.try_get_context("content_bucket_name") or "REPLACE_WITH_BUCKET_NAME",
            },
        )
        self.table.grant_read_write_data(self.content_adaptation_lambda)
        self.content_adaptation_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )
        # S3 read (fetch original content) + write (save adapted variant)
        self.content_adaptation_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject"],
                resources=["*"],  # Scope to content bucket ARN once provisioned
            )
        )

    # ======================================================================
    # API GATEWAY
    # ======================================================================

    def _build_api_gateway(self):

        # ------------------------------------------------------------------
        # Lambda Authorizer
        # Validates Cognito JWT + enforces RBAC on every request
        # Cached for 300s — cache key is the Authorization header value
        # ------------------------------------------------------------------
        authorizer_lambda = self._event_lambda(
            name="LambdaAuthorizer",
            entry="src/application/lambdas/authorizer",
            memory=256,
            timeout=10,
            extra_env={
                "COGNITO_USER_POOL_ID":  self.node.try_get_context("cognito_user_pool_id") or "REPLACE_WITH_POOL_ID",
                "COGNITO_CLIENT_ID":     self.node.try_get_context("cognito_client_id") or "REPLACE_WITH_CLIENT_ID",
                "COGNITO_REGION":        self.region,
            },
        )

        authorizer = apigw.TokenAuthorizer(
            self,
            "CampusIQAuthorizer",
            handler=authorizer_lambda,
            results_cache_ttl=Duration.seconds(300),
            identity_source="method.request.header.Authorization",
        )

        # ------------------------------------------------------------------
        # REST API
        # ------------------------------------------------------------------
        self.api = apigw.RestApi(
            self,
            "CampusIQApi",
            rest_api_name=f"campusiq-{self.deployment_name}-api",
            description=f"CampusIQ {self.deployment_name} REST API",
            deploy_options=apigw.StageOptions(
                stage_name="v1",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Authorization", "Content-Type"],
            ),
        )

        # Helper — Lambda integration
        def integration(fn: lambda_.Function) -> apigw.LambdaIntegration:
            return apigw.LambdaIntegration(fn, proxy=True)

        # Helper — add method with authorizer
        def add_proxy(resource: apigw.Resource, fn: lambda_.Function):
            """Add {proxy+} catch-all route pointing to fn."""
            proxy = resource.add_resource("{proxy+}")
            proxy.add_method("ANY", integration(fn), authorizer=authorizer)
            resource.add_method("ANY", integration(fn), authorizer=authorizer)

        # /courses → Courses Lambda
        courses_resource = self.api.root.add_resource("courses")
        add_proxy(courses_resource, self.courses_lambda)

        # /students → Students Lambda
        students_resource = self.api.root.add_resource("students")
        add_proxy(students_resource, self.students_lambda)

        # /tutor → Tutor Lambda
        tutor_resource = self.api.root.add_resource("tutor")
        add_proxy(tutor_resource, self.tutor_lambda)

        # /quiz → Quiz Lambda
        quiz_resource = self.api.root.add_resource("quiz")
        add_proxy(quiz_resource, self.quiz_lambda)

        # /teacher → Teacher Lambda
        teacher_resource = self.api.root.add_resource("teacher")
        add_proxy(teacher_resource, self.teacher_lambda)

        # /admin → Admin Lambda
        admin_resource = self.api.root.add_resource("admin")
        add_proxy(admin_resource, self.admin_lambda)

        CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            export_name=f"campusiq-{self.deployment_name}-api-url",
            description="CampusIQ API Gateway base URL",
        )

    # ======================================================================
    # EVENTBRIDGE RULES — wire events to target Lambdas
    # ======================================================================

    def _wire_eventbridge_rules(self):

        # QuizCompleted → Gap Detection Lambda
        events.Rule(
            self,
            "QuizCompletedRule",
            event_bus=self.event_bus,
            rule_name=f"campusiq-{self.deployment_name}-quiz-completed",
            description="Route QuizCompleted events to Gap Detection Lambda",
            event_pattern=events.EventPattern(
                source=["campusiq.quiz"],
                detail_type=["QuizCompleted"],
            ),
            targets=[targets.LambdaFunction(self.gap_detection_lambda)],
        )

        # GapDetected → Recommendation Lambda
        events.Rule(
            self,
            "GapDetectedRecommendationRule",
            event_bus=self.event_bus,
            rule_name=f"campusiq-{self.deployment_name}-gap-detected-recommendation",
            description="Route GapDetected events to Recommendation Lambda",
            event_pattern=events.EventPattern(
                source=["campusiq.gap"],
                detail_type=["GapDetected"],
            ),
            targets=[targets.LambdaFunction(self.recommendation_lambda)],
        )

        # GapDetected (severity > 0.85) → Content Adaptation Lambda
        # Note: severity filter applied inside the Lambda — EventBridge
        # does not support numeric comparisons in event patterns.
        # The Lambda checks severity and exits early if below threshold.
        events.Rule(
            self,
            "GapDetectedAdaptationRule",
            event_bus=self.event_bus,
            rule_name=f"campusiq-{self.deployment_name}-gap-detected-adaptation",
            description="Route GapDetected events to Content Adaptation Lambda (filters severity > 0.85 internally)",
            event_pattern=events.EventPattern(
                source=["campusiq.gap"],
                detail_type=["GapDetected"],
            ),
            targets=[targets.LambdaFunction(self.content_adaptation_lambda)],
        )

    # ======================================================================
    # PRIVATE HELPERS — Lambda factory methods
    # ======================================================================

    def _http_lambda(
        self,
        name: str,
        entry: str,
        memory: int,
        timeout: int,
        extra_env: dict,
    ) -> lambda_.Function:
        """
        HTTP Lambda — FastAPI + Mangum.

        Code.from_asset() zips the entire src/ directory at synth time.
        All shared modules (services/, routes/, schemas.py, models/) are
        available to every Lambda because they live under the same src/ root.

        Handler convention: {lambda_folder}/main.handler
        e.g. src/application/lambdas/courses/main.py → handler variable = handler
        Mangum wraps the FastAPI app as the Lambda handler.

        Handler string format: {module_path}.{function}
        With src/ as the asset root: application.lambdas.courses.main.handler
        """
        module_path = entry.replace("src/", "").replace("/", ".") + ".handler"

        return lambda_.Function(
            self,
            f"{name}Lambda",
            function_name=f"campusiq-{self.deployment_name}-{name.lower()}",
            code=lambda_.Code.from_asset(
                os.path.join(REPO_ROOT, "src"),
            ),
            handler=module_path,
            runtime=lambda_.Runtime.PYTHON_3_12,
            memory_size=memory,
            timeout=Duration.seconds(timeout),
            environment={**self.shared_env, **extra_env},
        )

    def _event_lambda(
        self,
        name: str,
        entry: str,
        memory: int,
        timeout: int,
        extra_env: dict,
    ) -> lambda_.Function:
        """
        Event-driven Lambda — plain handler function, no FastAPI.

        Same Code.from_asset(src/) approach as HTTP Lambdas.
        Handler convention: {lambda_folder}/handler.handler

        Handler string format: application.lambdas.stream_processor.handler.handler
        """
        module_path = entry.replace("src/", "").replace("/", ".") + ".handler"

        return lambda_.Function(
            self,
            f"{name}Lambda",
            function_name=f"campusiq-{self.deployment_name}-{name.lower().replace('_', '-')}",
            code=lambda_.Code.from_asset(
                os.path.join(REPO_ROOT, "src"),
            ),
            handler=module_path,
            runtime=lambda_.Runtime.PYTHON_3_12,
            memory_size=memory,
            timeout=Duration.seconds(timeout),
            environment={**self.shared_env, **extra_env},
        )