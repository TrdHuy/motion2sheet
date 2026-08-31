from pathlib import Path
from motion2sheet.anim2sheet.common.profile import load_character_profile, load_rig_profile
ROOT=Path(__file__).resolve().parents[3]; RIG=ROOT/"profiles/anim2sheet/rigs/game_humanoid_v2.json5"; CHARACTER=ROOT/"profiles/anim2sheet/characters/swordsman_v1.json5"
def test_game_humanoid_profile_owns_solver_and_topology_conventions():
    profile=load_rig_profile(RIG); assert profile["id"]=="game_humanoid_v2"; assert profile["authoringCapability"]=="humanoid_v2"; assert profile["semantics"]["chest"]=="Chest"; assert profile["solvers"]["arms"]["mode"]=="deterministic_joint_fk"; assert all("ikConstraint" not in cfg for cfg in profile["solvers"]["arms"]["sides"].values()); assert profile["solvers"]["legs"]["mode"]=="ik_with_explicit_knee_poles"; assert profile["solvers"]["legs"]["sides"]["left"]["poleAngleDeg"]==0; assert profile["solvers"]["legs"]["sides"]["right"]["poleAngleDeg"]==180
def test_swordsman_profile_owns_body_and_sword_construction_not_motion():
    profile=load_character_profile(CHARACTER); assert profile["rigProfile"]=="../rigs/game_humanoid_v2.json5"; sword=profile["equipment"][0]; assert sword["controller"]=="SwordController"; assert [row["object"] for row in sword["parts"]]==["SwordGrip","SwordBlade"]; assert sword["binding"]["primaryJoint"]=="leftWrist"; assert sword["binding"]["secondaryJoint"]=="rightWrist"; assert sword["binding"]["tipDistance"]==1.20
def test_animation_clips_have_no_python_author_implementation():
    package=ROOT/"motion2sheet/anim2sheet/animations"; assert not (package/"gale_slash/blender/author.py").exists(); assert not (package/"sword_idle").exists()
