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

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DomainConfig:
    """Domain-specific configuration for CampusIQ behaviour."""
    domain: str  # university | k12 | corporate
    tutor_persona: str
    guardrails_profile: str
    model_id: str
    temperature: float
    max_tokens: int
    age_group: str  # adult | teen | child
    content_restrictions: list[str]


class ExperiencePluginInterface(ABC):
    """Abstract base class for domain experience plugins.

    Controls how CampusIQ behaves for a specific deployment domain.
    """

    @abstractmethod
    def get_domain_config(self) -> DomainConfig:
        raise NotImplementedError

    @abstractmethod
    def get_guardrails_config(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_model_routing_config(self) -> dict:
        raise NotImplementedError