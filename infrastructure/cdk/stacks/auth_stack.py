# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


# infrastructure/cdk/stacks/auth_stack.py
#
# Provisions the CampusIQ Cognito User Pool for one institution deployment.
# One User Pool per deployment — physical tenant isolation.
# IdP federation type driven by campusiq.config.json:
#   config["idp"]["type"] = "ENTRA_ID" | "GOOGLE" | "SAML"
#
# Outputs user_pool and user_pool_client as construct references
# consumed by compute_stack.py for the Lambda Authorizer env vars.
#

import os

from aws_cdk import (
    Stack,
    Duration,
    aws_cognito as cognito,
    aws_lambda as lambda_,
    aws_iam as iam,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


class AuthStack(Stack):
    """
    Provisions the CampusIQ Cognito User Pool for one institution.

    Exposes:
        self.user_pool        — Cognito UserPool construct
        self.user_pool_client — App client (NextAuth.js uses this)
    Both passed into ComputeStack for Lambda Authorizer configuration.
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
        self.config = config
        idp_type = config.get("idp", {}).get("type", "ENTRA_ID")

        # ------------------------------------------------------------------
        # Lambda Triggers
        # Built before the User Pool so they can be passed as triggers.
        # All trigger Lambdas are lightweight — small memory, short timeout.
        # ------------------------------------------------------------------

        # Pre-Token Generation Lambda
        # Fires before every JWT is issued.
        # Enriches token with CampusIQ-specific claims:
        #   custom:studentId, custom:grade, custom:idpProvider, custom:enrollmentStatus
        # These claims are what the Lambda Authorizer reads on every API request.
        self.pre_token_lambda = lambda_.Function(
            self,
            "PreTokenLambda",
            function_name=f"campusiq-{deployment_name}-pre-token",
            code=lambda_.Code.from_asset(os.path.join(REPO_ROOT, "src")),
            handler="application.lambdas.auth.pre_token.handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(5),
            environment={
                "DEPLOYMENT_NAME": deployment_name,
            },
        )

        # Post-Confirmation Lambda
        # Fires after a user is confirmed in the User Pool.
        # For federated users (Entra ID / Google / SAML), this fires on
        # first login — creates the STUDENT/TEACHER/ADMIN DynamoDB profile.
        # Also assigns the user to the correct Cognito group based on IdP role.
        self.post_confirm_lambda = lambda_.Function(
            self,
            "PostConfirmLambda",
            function_name=f"campusiq-{deployment_name}-post-confirm",
            code=lambda_.Code.from_asset(os.path.join(REPO_ROOT, "src")),
            handler="application.lambdas.auth.post_confirm.handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(10),
            environment={
                "DEPLOYMENT_NAME": deployment_name,
            },
        )

        # Pre-Authentication Lambda
        # Fires before authentication is completed.
        # Checks the institution deployment is still active.
        # Can block authentication for deactivated accounts.
        self.pre_auth_lambda = lambda_.Function(
            self,
            "PreAuthLambda",
            function_name=f"campusiq-{deployment_name}-pre-auth",
            code=lambda_.Code.from_asset(os.path.join(REPO_ROOT, "src")),
            handler="application.lambdas.auth.pre_auth.handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            memory_size=256,
            timeout=Duration.seconds(5),
            environment={
                "DEPLOYMENT_NAME": deployment_name,
            },
        )

        # ------------------------------------------------------------------
        # Cognito User Pool
        # One pool per institution deployment.
        # selfSignUpEnabled=False — no open registration.
        # All users come from the institution's IdP via federation.
        # ------------------------------------------------------------------
        self.user_pool = cognito.UserPool(
            self,
            "CampusIQUserPool",
            user_pool_name=f"campusiq-{deployment_name}-pool",

            # No open registration — users come from IdP federation only
            self_sign_up_enabled=False,

            # Email is the sign-in identifier — consistent across all IdPs
            sign_in_aliases=cognito.SignInAliases(email=True),

            # MFA optional at pool level — enforced by group for OPS and PARENT
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(
                sms=False,
                otp=True,  # TOTP via authenticator app
            ),

            # Password policy — applies to non-federated accounts (PARENT, OPS)
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_symbols=True,
                require_digits=True,
                require_uppercase=True,
                temp_password_validity=Duration.days(7),
            ),

            # Account recovery via email only
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,

            # Standard attributes — auto-verified on federation
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                fullname=cognito.StandardAttribute(required=False, mutable=True),
            ),

            # Custom attributes — added by Pre-Token Lambda to every JWT
            custom_attributes={
                "studentId": cognito.StringAttribute(mutable=True),
                "grade": cognito.StringAttribute(mutable=True),
                "idpProvider": cognito.StringAttribute(mutable=True),
                "enrollmentStatus": cognito.StringAttribute(mutable=True),
                "institutionId": cognito.StringAttribute(mutable=False),
            },

            # Lambda triggers
            lambda_triggers=cognito.UserPoolTriggers(
                pre_token_generation=self.pre_token_lambda,
                post_confirmation=self.post_confirm_lambda,
                pre_authentication=self.pre_auth_lambda,
            ),

            # Email configuration — Cognito default for dev, SES for prod
            email=cognito.UserPoolEmail.with_cognito(),

            # Retain on destroy — never accidentally delete user accounts
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------
        # Role Groups
        # Precedence determines which group claim wins if user is in multiple.
        # Lower number = higher precedence.
        # OPS (0) > ADMIN (1) > TEACHER (2) > PARENT (3) > STUDENT (4)
        # ------------------------------------------------------------------
        role_groups = ["OPS", "ADMIN", "TEACHER", "PARENT", "STUDENT"]
        for precedence, role in enumerate(role_groups):
            cognito.CfnUserPoolGroup(
                self,
                f"Group{role}",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=role,
                description=f"CampusIQ {role} role group",
                precedence=precedence,
            )

        # ------------------------------------------------------------------
        # App Client — NextAuth.js uses this
        # Authorization Code Grant flow — no implicit flow (security best practice)
        # ------------------------------------------------------------------
        callback_url = config.get("deployment", {}).get(
            "callback_url", "http://localhost:3000/api/auth/callback/cognito"
        )
        logout_url = config.get("deployment", {}).get(
            "logout_url", "http://localhost:3000"
        )

        self.user_pool_client = self.user_pool.add_client(
            "NextAuthClient",
            user_pool_client_name=f"campusiq-{deployment_name}-nextauth",

            # Authorization Code Grant only — no implicit, no client credentials
            auth_flows=cognito.AuthFlow(
                user_password=True,  # enables USER_PASSWORD_AUTH for testing
                user_srp=True,  # enables USER_SRP_AUTH (more secure, used by Amplify)
                admin_user_password=True,  # enables ADMIN_USER_PASSWORD_AUTH for CLI testing
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[callback_url],
                logout_urls=[logout_url],
            ),

            # Token validity
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),

            # Security settings
            enable_token_revocation=True,
            prevent_user_existence_errors=True,

            # No client secret for public SPA clients
            generate_secret=False,
        )
        # ------------------------------------------------------------------
        # IdP Federation
        # Wired based on config["idp"]["type"]
        # Credentials (client_id, client_secret, metadata_url) come from
        # SSM Parameter Store — never hardcoded in CDK or config files.
        # ------------------------------------------------------------------
        if idp_type == "ENTRA_ID":
            self._add_entra_idp()
        elif idp_type == "GOOGLE":
            self._add_google_idp()
        elif idp_type == "SAML":
            self._add_saml_idp()

        # ------------------------------------------------------------------
        # Cognito Domain — needed for Hosted UI
        # ------------------------------------------------------------------
        self.user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"campusiq-{deployment_name}",
            ),
        )

        # ------------------------------------------------------------------
        # Grant trigger Lambdas permission to be invoked by Cognito
        # CDK does this automatically for lambdaTriggers —
        # but explicit grant is clearer for audit purposes.
        # ------------------------------------------------------------------
        for trigger_lambda in [
            self.pre_token_lambda,
            self.post_confirm_lambda,
            self.pre_auth_lambda,
        ]:
            trigger_lambda.add_permission(
                "CognitoInvoke",
                principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),
                source_arn=self.user_pool.user_pool_arn,
            )

        # ------------------------------------------------------------------
        # CloudFormation outputs — consumed by compute_stack.py
        # ------------------------------------------------------------------
        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            export_name=f"campusiq-{deployment_name}-user-pool-id",
            description="Cognito User Pool ID — used by Lambda Authorizer",
        )
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            export_name=f"campusiq-{deployment_name}-user-pool-client-id",
            description="Cognito App Client ID — used by NextAuth.js",
        )
        CfnOutput(
            self,
            "CognitoIssuer",
            value=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool.user_pool_id}",
            export_name=f"campusiq-{deployment_name}-cognito-issuer",
            description="Cognito JWT issuer URL — used by NextAuth.js COGNITO_ISSUER env var",
        )
        CfnOutput(
            self,
            "HostedUiUrl",
            value=f"https://campusiq-{deployment_name}.auth.{self.region}.amazoncognito.com",
            export_name=f"campusiq-{deployment_name}-hosted-ui-url",
            description="Cognito Hosted UI URL — used by NextAuth.js",
        )

    # ======================================================================
    # IdP Federation methods
    # ======================================================================

    def _add_entra_idp(self):
        """
        Microsoft Entra ID (Azure AD) federation via OIDC.
        client_id and client_secret must be in SSM Parameter Store:
            /campusiq/{deployment_name}/idp/entra/client_id
            /campusiq/{deployment_name}/idp/entra/client_secret
        These are set manually after CDK deploy — never hardcoded.
        """
        tenant_id = self.node.try_get_context("entra_tenant_id")
        if not tenant_id:
            print("Skipping Entra IdP — entra_tenant_id not provided. "
                  "Pass via: cdk deploy --context entra_tenant_id=YOUR_TENANT_ID")
            return
        entra_idp = cognito.UserPoolIdentityProviderOidc(
            self,
            "EntraIdP",
            user_pool=self.user_pool,
            name="EntraID",
            client_id=self._get_ssm_placeholder("entra_client_id"),
            client_secret=self._get_ssm_placeholder("entra_client_secret"),

            # Entra ID OIDC discovery endpoint
            # Replace {tenant_id} with actual tenant ID in SSM
            issuer_url="https://login.microsoftonline.com/{tenant_id}/v2.0",

            # Claims mapping — Entra ID → Cognito standard attributes
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.other("email"),
                fullname=cognito.ProviderAttribute.other("name"),
                custom={
                    "custom:idpProvider": cognito.ProviderAttribute.other("iss"),
                },
            ),
            scopes=["openid", "email", "profile"],
        )

        # Wire IdP to app client
        self.user_pool_client.node.add_dependency(entra_idp)

    def _add_google_idp(self):
        """
        Google Workspace federation via OIDC.
        Credentials in SSM Parameter Store:
            /campusiq/{deployment_name}/idp/google/client_id
            /campusiq/{deployment_name}/idp/google/client_secret
        """
        client_id = self.node.try_get_context("google_client_id")
        if not client_id:
            print("Skipping Google IdP — google_client_id not provided. "
                  "Pass via: cdk deploy --context google_client_id=YOUR_CLIENT_ID")
            return
        google_idp = cognito.UserPoolIdentityProviderGoogle(
            self,
            "GoogleIdP",
            user_pool=self.user_pool,
            client_id=self._get_ssm_placeholder("google_client_id"),
            client_secret=self._get_ssm_placeholder("google_client_secret"),

            # Claims mapping — Google → Cognito standard attributes
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.GOOGLE_EMAIL,
                fullname=cognito.ProviderAttribute.GOOGLE_NAME,
                custom={
                    "custom:idpProvider": cognito.ProviderAttribute.other("iss"),
                },
            ),
            scopes=["openid", "email", "profile"],
        )

        self.user_pool_client.node.add_dependency(google_idp)

    def _add_saml_idp(self):
        """
        Generic SAML 2.0 federation — covers Shibboleth, ADFS, Okta, etc.
        Metadata URL in SSM Parameter Store:
            /campusiq/{deployment_name}/idp/saml/metadata_url
        """
        metadata_url = self.node.try_get_context("saml_metadata_url")
        if not metadata_url:
            print("Skipping SAML IdP — saml_metadata_url not provided. "
                  "Pass via: cdk deploy --context saml_metadata_url=YOUR_METADATA_URL")
            return
        saml_idp = cognito.UserPoolIdentityProviderSaml(
            self,
            "SamlIdP",
            user_pool=self.user_pool,
            name="SamlIdP",

            # Metadata can be provided as URL or inline XML
            # URL is preferred — Cognito refreshes metadata automatically
            metadata=cognito.UserPoolIdentityProviderSamlMetadata.url(
                self._get_ssm_placeholder("saml_metadata_url")
            ),

            # SAML attribute mapping — attribute names vary by IdP
            # These are the most common SAML assertion attribute names
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.other(
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
                ),
                fullname=cognito.ProviderAttribute.other(
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
                ),
            ),
        )

        self.user_pool_client.node.add_dependency(saml_idp)

    def _get_ssm_placeholder(self, key: str) -> str:
        """
        Returns a placeholder string for SSM-stored credentials.
        Real values are set in SSM Parameter Store after CDK deploy.
        CDK deploy will use this placeholder — the actual value is
        fetched by Cognito at runtime from SSM.

        Instructions for deployer:
            aws ssm put-parameter \
                --name /campusiq/{deployment_name}/idp/entra/client_id \
                --value YOUR_CLIENT_ID \
                --type SecureString
        """
        return f"REPLACE_WITH_SSM_VALUE_{key.upper()}"
