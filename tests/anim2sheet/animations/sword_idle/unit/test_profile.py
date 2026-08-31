from pathlib import Path

from motion2sheet.anim2sheet.common.profile import resolve_review_request


ROOT = Path(__file__).resolve().parents[5]
IDLE = ROOT / "profiles/anim2sheet/animations/sword_idle/animation.json5"
GALE = ROOT / "profiles/anim2sheet/animations/gale_slash/animation.json5"
CAMERAS = ROOT / "profiles/anim2sheet/cameras/fast_keypose_review.json"


def resolve(profile: Path):
    return resolve_review_request(
        profile_path=profile,
        camera_profile_path=CAMERAS,
        frames=None,
        cameras=None,
    )


def test_sword_idle_is_profile_only_clip_on_shared_authoring_stack():
    idle = resolve(IDLE)
    gale = resolve(GALE)
    assert idle["animation"] == "sword_idle"
    assert idle["contractFrames"] == [1, 2, 3, 4]
    assert idle["executionFrames"] == [1, 2, 3, 4]
    assert idle["authoringCapability"] == gale["authoringCapability"] == "humanoid_v2"
    assert idle["rigProfilePath"] == gale["rigProfilePath"]
    assert idle["characterProfilePath"] == gale["characterProfilePath"]
    assert idle["source"]["generator"] == "profile-driven-humanoid-v1"
    assert not (ROOT / "motion2sheet/anim2sheet/animations/sword_idle").exists()
