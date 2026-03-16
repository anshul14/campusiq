# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from src.application.plugins.experience_plugin_interface.base import (
    ExperiencePluginInterface, DomainConfig
)


class CustomExperiencePlugin(ExperiencePluginInterface):
    """
    Template for building a custom experience plugin for CampusIQ.

    An experience plugin controls how CampusIQ behaves for a
    specific deployment domain — the AI tutor's persona, which
    Bedrock model is used, content restrictions, and guardrails.

    Steps to implement:
    1. Rename this class to match your domain
       (e.g. CorporateExperiencePlugin)
    2. Implement all three methods below
    3. Set the domain value in get_domain_config()
    4. Register your plugin in campusiq.config.json

    See docs/experience-plugin-guide/ for full documentation.
    """

    def __init__(self, config: dict):
        """
        Initialise with configuration from campusiq.config.json.

        Args:
            config: Domain-specific config block from
                    campusiq.config.json under domain
        """
        self.config = config

    def get_domain_config(self) -> DomainConfig:
        """
        Return the domain configuration for this experience.

        Returns:
            DomainConfig with tutor persona, model settings,
            age group, and content restrictions
        """
        raise NotImplementedError

    def get_guardrails_config(self) -> dict:
        """
        Return the Amazon Bedrock Guardrails configuration
        for this domain.

        K-12 and kindergarten should use strict content filtering.
        University and corporate can use standard filtering.

        Returns:
            Dict with guardrails_id and guardrails_version
        """
        raise NotImplementedError

    def get_model_routing_config(self) -> dict:
        """
        Return model routing configuration — which Bedrock model
        to use for each agent in this domain.

        Returns:
            Dict mapping agent names to model IDs and parameters:
            {
                "tutor": {"model_id": "...", "temperature": 0.7},
                "assessment": {"model_id": "...", "temperature": 0.4},
                ...
            }
        """
        raise NotImplementedError
