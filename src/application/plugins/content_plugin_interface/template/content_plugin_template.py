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

from src.application.plugins.content_plugin_interface.base import (
    ContentPluginInterface, CPIRequest, CPIContent
)


class CustomCMSPlugin(ContentPluginInterface):
    """
    Template for building a custom CMS plugin for CampusIQ.

    Replace this docstring with your CMS name and a brief description
    of what it connects to.

    Steps to implement:
    1. Rename this class to match your CMS (e.g. MoodlePlugin)
    2. Implement all five methods below
    3. Each method receives a CPIRequest and must return the
       specified type
    4. Add the Apache 2.0 license header to this file
    5. Register your plugin in campusiq.config.json

    See docs/cms-plugin-guide/ for full documentation.
    """

    def __init__(self, config: dict):
        """
        Initialise your plugin with configuration from
        campusiq.config.json.

        Args:
            config: Plugin-specific config block from
                    campusiq.config.json under plugins.<your_plugin>
        """
        self.config = config

    def fetch_content(self, request: CPIRequest) -> CPIContent:
        """
        Fetch a single content item from your CMS by course and
        module ID.

        Args:
            request: CPIRequest with course_id and module_id set

        Returns:
            CPIContent — standardised content object
        """
        raise NotImplementedError

    def search_content(self, request: CPIRequest) -> list[CPIContent]:
        """
        Search for content items matching a query string.

        Args:
            request: CPIRequest with query and optional filters set

        Returns:
            List of CPIContent objects matching the query
        """
        raise NotImplementedError

    def list_courses(self, request: CPIRequest) -> list[dict]:
        """
        List all available courses from your CMS.

        Args:
            request: CPIRequest with optional filters

        Returns:
            List of dicts with at minimum: course_id, title,
            description, domain
        """
        raise NotImplementedError

    def get_metadata(self, request: CPIRequest) -> dict:
        """
        Return metadata for a specific content item.

        Args:
            request: CPIRequest with course_id and module_id set

        Returns:
            Dict with content metadata — domain, difficulty,
            content_type, last_updated
        """
        raise NotImplementedError

    def ingest_content(self, request: CPIRequest) -> dict:
        """
        Trigger ingestion of content into the CampusIQ
        knowledge base pipeline.

        Args:
            request: CPIRequest with course_id and module_id set

        Returns:
            Dict with ingestion status — job_id, status, message
        """
        raise NotImplementedError