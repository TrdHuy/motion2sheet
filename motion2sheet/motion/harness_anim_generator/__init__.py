"""Skill-Driven Agent Runtime for supervised Humanoid Motion authoring."""

from .contracts import GenerationRequest, GenerationResult, HarnessError, ProviderError

__all__ = [
    "AnimationGenerationOrchestrator",
    "GenerationRequest",
    "GenerationResult",
    "HarnessError",
    "ProviderError",
]


def __getattr__(name: str):
    if name == "AnimationGenerationOrchestrator":
        from .orchestrator import AnimationGenerationOrchestrator

        return AnimationGenerationOrchestrator
    raise AttributeError(name)
