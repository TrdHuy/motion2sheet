"""FBX-specific source-format preservation for round-trip POC."""

from .native import extract_fbx_authority, patch_generated_fbx

__all__ = ["extract_fbx_authority", "patch_generated_fbx"]
