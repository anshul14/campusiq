# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
post-confirm lambda:
    Fires on first login for federated users.
    Creates the DynamoDB student profile if it doesn't exist.
"""

import logging
from datetime import datetime, timezone

from application.services import dynamodb as db

logger = logging.getLogger(__name__)


def handler(event, context):
    logger.info(f"Post-Confirm triggered for {event['userName']} via {event['triggerSource']}")

    # Step1. Extract user attributes
    user_attributes = event["request"]["userAttributes"]
    try:
        db.create_student_profile_if_not_exists(
            user_id=event["userName"],
            email=user_attributes.get("email", ""),
            name=user_attributes.get("name", ""),
            grade=user_attributes.get("custom:grade", ""),
            idp_provider=user_attributes.get("custom:idpProvider", ""),
            institution_id=user_attributes.get("custom:institutionId", ""),
            entity_type="STUDENT",
            created_at=datetime.now(timezone.utc).isoformat()

        )
    except Exception as e:
        logger.error(f"Failed to create profile for {event['userName']}", extra={"error": str(e)})
        raise  # re-raise so Cognito knows the trigger failed

    return event
