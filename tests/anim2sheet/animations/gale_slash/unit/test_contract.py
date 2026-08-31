from pathlib import Path
import pytest
from motion2sheet.anim2sheet.common.profile import resolve_execution_frames, resolve_motion_profile
MOTION=Path("profiles/anim2sheet/animations/gale_slash/motion.json")
def motion(): return resolve_motion_profile(MOTION)["profile"]
def test_canonical_motion_is_full_f1_f16():
    value=motion(); assert [row["frame"] for row in value["frames"]]==list(range(1,17)); assert resolve_execution_frames(value,None)==list(range(1,17))
def test_execution_subset_does_not_mutate_motion():
    value=motion(); assert resolve_execution_frames(value,"7,8")==[7,8]; assert [row["frame"] for row in value["frames"]]==list(range(1,17))
def test_frame_outside_motion_fails_fast():
    with pytest.raises(ValueError,match="outside motion frames"): resolve_execution_frames(motion(),"17")
