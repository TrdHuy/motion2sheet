from __future__ import annotations

from pathlib import Path

from motion2sheet.anim2sheet.common.camera.config import load_camera_profile, resolve_camera_names

from .config import load_pose_reference, load_profile
from .contract import load_joint_contract, resolve_execution_frames

ANIMATION_NAME = "gale_slash"


def resolve_review_request(*, profile_path: Path, joint_contract_path: Path, camera_profile_path: Path,
                           frames: str | None, cameras: str | None) -> dict:
    profile_path = profile_path.resolve()
    joint_contract_path = joint_contract_path.resolve()
    camera_profile_path = camera_profile_path.resolve()
    profile = load_profile(profile_path)
    reference_path, reference = load_pose_reference(profile_path, profile)
    contract = load_joint_contract(joint_contract_path)
    execution_frames = resolve_execution_frames(contract, frames)
    camera_profile = load_camera_profile(camera_profile_path)
    camera_names = resolve_camera_names(camera_profile, cameras)
    source = dict(profile)
    source.update({
        "animation": ANIMATION_NAME,
        "generator": "deterministic-joint-fk-registry-v1",
        "reviewMode": "review",
        "executionFrames": execution_frames,
        "poseReferenceSource": str(reference_path),
        "poseReferenceData": reference,
        "armJointContractSource": str(joint_contract_path),
        "cameraProfileSource": str(camera_profile_path),
    })
    return {
        "animation": ANIMATION_NAME,
        "profilePath": profile_path,
        "jointContractPath": joint_contract_path,
        "cameraProfilePath": camera_profile_path,
        "profile": profile,
        "referencePath": reference_path,
        "reference": reference,
        "contract": contract,
        "contractFrames": [int(v) for v in contract["reviewFrames"]],
        "executionFrames": execution_frames,
        "cameraProfile": camera_profile,
        "cameraNames": camera_names,
        "source": source,
    }
