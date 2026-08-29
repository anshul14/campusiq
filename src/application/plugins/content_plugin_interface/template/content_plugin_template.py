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

from application.plugins.content_plugin_interface.base import (
    ContentPlugin,
    ContentNotFoundError,
    CPIContent,
    CPIMetadata,
    CPIIngestionResult,
    ContentType,
    IngestionStatus,
)


class CustomCMSPlugin(ContentPlugin):
    """
    Template for building a custom CMS plugin for CampusIQ.

    Replace this docstring with your CMS name and a brief description
    of what it connects to.

    Steps to implement:
    1. Rename this class to match your CMS (e.g. MoodlePlugin)
    2. Implement all SIX methods below (fetch_content, search_content,
       list_courses, list_modules, get_metadata, ingest_content) —
       list_modules exists specifically so a freshly-connected plugin
       can discover pre-existing content it has no other way to find
       (fetch_content requires an already-known module_id)
    3. Each method takes typed individual arguments, NOT a single
       request object — every plugin implements the exact same
       signatures as ContentPlugin (base.py); don't invent your own
    4. Raise ContentNotFoundError (not a generic exception) when
       content genuinely doesn't exist — callers rely on being able to
       catch this one consistently across every plugin
    5. Add the Apache 2.0 license header to this file
    6. Register your plugin in campusiq.config.json under
       plugins.<your_plugin_name> — that block is exactly what gets
       passed to __init__ below

    See docs/cms-plugin-guide/ for full documentation.
    """

    def __init__(self, config: dict):
        """
        Initialise your plugin from its config block in
        campusiq.config.json (plugins.<your_plugin_name>). Standardised
        across every plugin so a plugin registry can construct any of
        them the same way — PluginClass(config=plugin_config_block) —
        without special-casing each CMS's constructor.

        Validate what you need here and fail loudly (raise ValueError)
        on a missing required key, rather than letting a bad config
        surface as a confusing error later, mid-request.

        Args:
            config: this plugin's own config block only — e.g. for a
                    plugin needing an API endpoint and key, something
                    like {"base_url": "...", "api_key": "..."}
        """
        self.config = config

    def fetch_content(self, course_id: str, module_id: str) -> CPIContent:
        """
        Fetch a single content item from your CMS by course and
        module ID. Raise ContentNotFoundError if it doesn't exist.
        """
        raise NotImplementedError

    def search_content(self, query: str, filters: dict | None = None) -> list[CPIContent]:
        """Search for content items matching a query string."""
        raise NotImplementedError

    def list_courses(self) -> list[dict]:
        """
        List all available courses from your CMS.

        Returns:
            List of dicts with at minimum: course_id, title. A plain
            dict, not a typed dataclass — no CPICourse type exists;
            list_courses and list_modules return dicts deliberately
            (see base.py) rather than introduce a new type without a
            specified need.
        """
        raise NotImplementedError

    def list_modules(self, course_id: str) -> list[dict]:
        """
        List all modules/content items within a given course. This is
        what makes initial sync/backfill possible — without it, a
        plugin has no way to discover content in a course it hasn't
        seen before.

        Returns:
            List of dicts with at minimum: module_id, title,
            content_type.
        """
        raise NotImplementedError

    def get_metadata(self, content_id: str) -> CPIMetadata:
        """
        Return metadata for a specific content item without fetching
        its full body. Raise ContentNotFoundError if it doesn't exist.

        Returns:
            CPIMetadata — domain/difficulty should be None if your CMS
            genuinely doesn't carry that information, rather than
            guessing a default. domain in particular drives Bedrock
            Guardrails profile selection downstream, so a wrong guess
            is a safety-relevant bug, not a cosmetic one.
        """
        raise NotImplementedError

    def ingest_content(self, course_id: str, module_id: str) -> CPIIngestionResult:
        """
        Trigger ingestion of a content item into the CampusIQ
        knowledge base pipeline — pulls from your CMS and writes the
        result into CampusIQ's own store.

        Returns:
            CPIIngestionResult — module_id, s3_key, ingestion_status,
            and on failure, error_message (return a FAILED result
            rather than raising, so a bulk sync run can report partial
            failures instead of aborting entirely).
        """
        raise NotImplementedError