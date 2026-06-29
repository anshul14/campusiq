# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
pre-token lambda:
    Called by Cognito before issuing every JWT.
    Adds custom claims to JWT
"""

import logging

logger = logging.getLogger(__name__)

def handler(event, context):
    logger.info(f"Pre-Token triggered for {event['userName']} via {event['triggerSource']}")
    # Extract information from request
    groups = event["request"]["groupConfiguration"].get("groupsToOverride", [])
    role = groups[0] if groups else "STUDENT"
    grade = event["request"]["userAttributes"].get("custom:grade", "")
    idp_provider = event["request"]["userAttributes"].get("custom:idpProvider", "")
    user_id = event["userName"]

    # Add as claimsoverride in the response
    event["response"]["claimsOverrideDetails"] = {
        "claimsToAddOrOverride": {
            "role": role,
            "userId": user_id,
            "grade": grade,
            "idpProvider": idp_provider,
        }
    }

    # Return event
    return event

