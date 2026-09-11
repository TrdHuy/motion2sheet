from __future__ import annotations

from typing import Protocol

from ..contracts import ProviderRequest, ProviderResponse


class AIProvider(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Send one structured operation to an AI engine."""
