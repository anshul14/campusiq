# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

import json
import logging
import os
import urllib.request

from jose import jwt, JWTError

logger = logging.getLogger(__name__)

# Module-level cache — persists across warm invocations
_jwks_cache = None


def _get_jwks(jwks_url: str) -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        with urllib.request.urlopen(jwks_url) as response:
            _jwks_cache = json.loads(response.read().decode())
    return _jwks_cache


def handler(event, context):
    logger.info(f"Authorizer invoked for {event.get('methodArn')}")
    # Extract JWT from the event
    token = event["authorizationToken"].replace("Bearer ", "")
    # Validate it agains JWKS endpoint
    region = os.environ["COGNITO_REGION"]
    user_pool_id = os.environ["COGNITO_USER_POOL_ID"]
    client_id = os.environ["COGNITO_CLIENT_ID"]

    jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"

    try:
        jwks = _get_jwks(jwks_url)

        claims = jwt.decode(token, jwks, algorithms=["RS256"], audience=client_id)

        # Extract claims and build the response
        user_id = claims["sub"]
        role = claims.get("role", "STUDENT")
        email = claims.get("email", "")
        grade = claims.get("custom:grade", "")

        return {
            "principalId": user_id,
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": event["methodArn"],
                }]
            },
            "context": {
                "userId": user_id,
                "role": role,
                "email": email,
                "grade": grade,
            }
        }
    except JWTError as e:
        logger.error(f"JWT validation failed: {str(e)}")
        raise Exception("Unauthorized")
    except Exception as e:
        logger.error(f"Authorizer error: {str(e)}")
        raise Exception("Unauthorized")
