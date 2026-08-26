"""Compatibility facade for motion2sheet.motion.common.io."""

from .motion.common.io import read_json, write_json, write_pose_sequence

__all__ = ["read_json", "write_json", "write_pose_sequence"]
