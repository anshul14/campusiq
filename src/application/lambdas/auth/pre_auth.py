# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
pre-auth lambda:
    This Lambda is fired before authentication completes.
"""

import logging

logger = logging.getLogger(__name__)


def handler(event, context):
    logger.info(f"Pre-auth triggered for {event['userName']} via {event['triggerSource']}")

    return event
