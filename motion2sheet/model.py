"""Compatibility facade for motion2sheet.motion.common.model."""

from .motion.common.model import BONES, CANONICAL_JOINTS, Point, PoseFrame, PoseSequence, missing_joints

__all__ = ["BONES", "CANONICAL_JOINTS", "Point", "PoseFrame", "PoseSequence", "missing_joints"]
