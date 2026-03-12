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

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CPIContent:
    """Standard content object returned by all CMS plugins."""
    content_id: str
    title: str
    body: str
    media_urls: list[str]
    metadata: dict
    source: str
    request_id: str


@dataclass
class CPIRequest:
    """Standard request object passed to all CMS plugin actions."""
    action: str  # fetchContent | searchContent | listCourses | getMetadata | ingestContent
    course_id: Optional[str] = None
    module_id: Optional[str] = None
    query: Optional[str] = None
    filters: Optional[dict] = None
    request_id: Optional[str] = None


class ContentPluginInterface(ABC):
    """Abstract base class for all CampusIQ CMS plugins.

    Every CMS plugin must implement this interface.
    The plugin is responsible for translating CMS-specific
    content into the standard CPIContent format.
    """

    @abstractmethod
    def fetch_content(self, request: CPIRequest) -> CPIContent:
        raise NotImplementedError

    @abstractmethod
    def search_content(self, request: CPIRequest) -> list[CPIContent]:
        raise NotImplementedError

    @abstractmethod
    def list_courses(self, request: CPIRequest) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, request: CPIRequest) -> dict:
        raise NotImplementedError

    @abstractmethod
    def ingest_content(self, request: CPIRequest) -> dict:
        raise NotImplementedError