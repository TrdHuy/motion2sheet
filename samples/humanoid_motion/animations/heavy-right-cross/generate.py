from __future__ import annotations
import argparse,json,math
from pathlib import Path
from motion2sheet.motion.humanoid_motion.schema import (
    ANIMATION_SCHEMA,
    CANONICAL_SKELETON_ID,
    EXPECTED_COORDINATE_SYSTEM,
    EXPECTED_QUATERNION_CONVENTION,
    ROTATION_JOINTS,
    validate_animation,
)
ANIMATION_ID = 'heavy-right-cross'
FPS = 8.0
FRAME_COUNT = 10
DURATION_SECONDS = (FRAME_COUNT - 1) / FPS
QUANTIZE_DIGITS = 12

# Locked Heavy Right Cross. RightHand X twist at F4-F8 only changes wrist roll
# around the attack axis; upper/lower arm trajectory and F5 impact line stay frozen.
_POSES = [
{'Hips':(0,0,-8),'Spine':(1,0,-6),'Chest':(2,0,-8),'Neck':(0,0,2),'Head':(0,0,0),'LeftShoulder':(0,0,-4),'LeftUpperArm':(0,45,-10),'LeftLowerArm':(0,-135,-10),'LeftHand':(0,-125,-8),'RightShoulder':(0,0,5),'RightUpperArm':(0,-40,25),'RightLowerArm':(0,118,30),'RightHand':(0,108,26),'LeftUpperLeg':(-12,-7,-3),'LeftLowerLeg':(8,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(10,9,4),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,5),'RightToe':(0,0,0)},
{'Hips':(0,0,-13),'Spine':(0,0,-9),'Chest':(1,0,-11),'Neck':(0,0,2),'Head':(0,0,0),'LeftShoulder':(0,0,-4),'LeftUpperArm':(0,45,-10),'LeftLowerArm':(0,-135,-10),'LeftHand':(0,-125,-8),'RightShoulder':(0,0,2),'RightUpperArm':(0,-42,23),'RightLowerArm':(0,120,29),'RightHand':(0,110,25),'LeftUpperLeg':(-13,-7,-3),'LeftLowerLeg':(8,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(11,9,7),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,10),'RightToe':(0,0,0)},
{'Hips':(-1,0,-20),'Spine':(-1,0,-14),'Chest':(-2,0,-12),'Neck':(0,0,2),'Head':(0,0,0),'LeftShoulder':(0,0,-4),'LeftUpperArm':(0,45,-10),'LeftLowerArm':(0,-135,-10),'LeftHand':(0,-125,-8),'RightShoulder':(0,0,-2),'RightUpperArm':(0,-44,20),'RightLowerArm':(0,122,27),'RightHand':(0,112,24),'LeftUpperLeg':(-14,-8,-4),'LeftLowerLeg':(9,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(12,10,12),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,15),'RightToe':(0,0,0)},
{'Hips':(0,0,-2),'Spine':(-1,0,-11),'Chest':(-1,0,-9),'Neck':(0,0,1),'Head':(0,0,0),'LeftShoulder':(0,0,-5),'LeftUpperArm':(0,45,-11),'LeftLowerArm':(0,-135,-11),'LeftHand':(0,-125,-9),'RightShoulder':(0,0,4),'RightUpperArm':(0,-42,25),'RightLowerArm':(0,120,28),'RightHand':(0,110,24),'LeftUpperLeg':(-13,-7,-3),'LeftLowerLeg':(8,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(11,9,16),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,20),'RightToe':(0,0,0)},
{'Hips':(2,0,14),'Spine':(3,0,6),'Chest':(4,0,4),'Neck':(0,0,0),'Head':(0,0,0),'LeftShoulder':(0,0,-6),'LeftUpperArm':(0,44,-12),'LeftLowerArm':(0,-134,-12),'LeftHand':(0,-124,-10),'RightShoulder':(0,0,15),'RightUpperArm':(0,-18,65),'RightLowerArm':(0,40,72),'RightHand':(45,30,70),'LeftUpperLeg':(-12,-6,-2),'LeftLowerLeg':(7,4,0),'LeftFoot':(3,3,-1),'LeftToe':(0,0,0),'RightUpperLeg':(10,8,22),'RightLowerLeg':(-5,-5,0),'RightFoot':(-3,-3,28),'RightToe':(0,0,0)},
{'Hips':(3,0,26),'Spine':(5,0,20),'Chest':(7,0,28),'Neck':(0,0,-2),'Head':(0,0,0),'LeftShoulder':(0,0,-7),'LeftUpperArm':(0,43,-14),'LeftLowerArm':(0,-132,-14),'LeftHand':(0,-122,-12),'RightShoulder':(0,0,24),'RightUpperArm':(0,-4,88),'RightLowerArm':(0,-2,90),'RightHand':(90,0,90),'LeftUpperLeg':(-11,-5,-1),'LeftLowerLeg':(7,4,0),'LeftFoot':(3,2,-1),'LeftToe':(0,0,0),'RightUpperLeg':(9,7,28),'RightLowerLeg':(-4,-4,0),'RightFoot':(-2,-2,36),'RightToe':(0,0,0)},
{'Hips':(4,0,30),'Spine':(6,0,24),'Chest':(8,0,33),'Neck':(0,0,-3),'Head':(0,0,0),'LeftShoulder':(0,0,-7),'LeftUpperArm':(0,42,-14),'LeftLowerArm':(0,-130,-14),'LeftHand':(0,-120,-12),'RightShoulder':(0,0,28),'RightUpperArm':(0,-2,94),'RightLowerArm':(0,-4,94),'RightHand':(90,-2,94),'LeftUpperLeg':(-10,-4,0),'LeftLowerLeg':(6,3,0),'LeftFoot':(3,2,0),'LeftToe':(0,0,0),'RightUpperLeg':(8,6,30),'RightLowerLeg':(-4,-4,0),'RightFoot':(-2,-2,38),'RightToe':(0,0,0)},
{'Hips':(2,0,12),'Spine':(3,0,10),'Chest':(4,0,12),'Neck':(0,0,0),'Head':(0,0,0),'LeftShoulder':(0,0,-6),'LeftUpperArm':(0,44,-12),'LeftLowerArm':(0,-134,-12),'LeftHand':(0,-124,-10),'RightShoulder':(0,0,12),'RightUpperArm':(0,-35,35),'RightLowerArm':(0,108,38),'RightHand':(45,98,30),'LeftUpperLeg':(-11,-5,-1),'LeftLowerLeg':(7,4,0),'LeftFoot':(3,2,-1),'LeftToe':(0,0,0),'RightUpperLeg':(9,7,18),'RightLowerLeg':(-5,-5,0),'RightFoot':(-3,-3,22),'RightToe':(0,0,0)},
{'Hips':(1,0,-2),'Spine':(1,0,-2),'Chest':(2,0,-4),'Neck':(0,0,1),'Head':(0,0,0),'LeftShoulder':(0,0,-5),'LeftUpperArm':(0,45,-11),'LeftLowerArm':(0,-135,-11),'LeftHand':(0,-125,-9),'RightShoulder':(0,0,7),'RightUpperArm':(0,-38,28),'RightLowerArm':(0,114,32),'RightHand':(15,104,28),'LeftUpperLeg':(-12,-6,-2),'LeftLowerLeg':(8,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(10,8,9),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,11),'RightToe':(0,0,0)},
{'Hips':(0,0,-7),'Spine':(1,0,-5),'Chest':(2,0,-7),'Neck':(0,0,2),'Head':(0,0,0),'LeftShoulder':(0,0,-4),'LeftUpperArm':(0,45,-10),'LeftLowerArm':(0,-135,-10),'LeftHand':(0,-125,-8),'RightShoulder':(0,0,5),'RightUpperArm':(0,-40,25),'RightLowerArm':(0,118,30),'RightHand':(0,108,26),'LeftUpperLeg':(-12,-7,-3),'LeftLowerLeg':(8,5,0),'LeftFoot':(4,3,-2),'LeftToe':(0,0,0),'RightUpperLeg':(10,9,5),'RightLowerLeg':(-6,-6,0),'RightFoot':(-4,-4,6),'RightToe':(0,0,0)}]
_HIPS_TRANSLATIONS=[(-0.01,0.0,0.0),(-0.005,0.02,-0.01),(0.0,0.035,-0.018),(0.005,0.012,-0.024),(0.008,-0.02,-0.03),(0.01,-0.05,-0.04),(0.008,-0.055,-0.035),(0.0,-0.018,-0.022),(-0.006,-0.005,-0.01),(-0.01,0.0,0.0)]
def _clean(value):
    result=round(float(value),QUANTIZE_DIGITS); return 0.0 if result==0.0 else result
def _multiply(a,b):
    aw,ax,ay,az=a; bw,bx,by,bz=b
    return [aw*bw-ax*bx-ay*by-az*bz,aw*bx+ax*bw+ay*bz-az*by,aw*by-ax*bz+ay*bw+az*bx,aw*bz+ax*by-ay*bx+az*bw]
def _normalize(q):
    n=math.sqrt(sum(c*c for c in q));
    if n<=0 or not math.isfinite(n): raise ValueError('cannot normalize invalid quaternion')
    return [_clean(c/n) for c in q]
def _euler_quaternion(v):
    hx,hy,hz=[math.radians(float(x))*0.5 for x in v]
    qx=[math.cos(hx),math.sin(hx),0.0,0.0]; qy=[math.cos(hy),0.0,math.sin(hy),0.0]; qz=[math.cos(hz),0.0,0.0,math.sin(hz)]
    return _normalize(_multiply(qz,_multiply(qy,qx)))
def _rotation_track(semantic):
    track=[]
    for pose in _POSES:
        q=_euler_quaternion(pose.get(semantic,(0.0,0.0,0.0)))
        if track and sum(a*b for a,b in zip(track[-1],q))<0: q=[_clean(-c) for c in q]
        if not track:
            first_nonzero=next((c for c in q if abs(c)>1e-15),0.0)
            if first_nonzero<0:q=[_clean(-c) for c in q]
        track.append(q)
    return track
def build_animation():
    identity=[1.0,0.0,0.0,0.0]
    return {'schema':ANIMATION_SCHEMA,'version':1,'id':ANIMATION_ID,'canonicalSkeleton':CANONICAL_SKELETON_ID,'durationSeconds':DURATION_SECONDS,'fps':FPS,'frameCount':FRAME_COUNT,'loop':False,'coordinateSystem':dict(EXPECTED_COORDINATE_SYSTEM),'quaternionConvention':dict(EXPECTED_QUATERNION_CONVENTION),'root':{'translations':[[0.0,0.0,0.0] for _ in range(FRAME_COUNT)],'rotations':[identity[:] for _ in range(FRAME_COUNT)]},'hips':{'translations':[[_clean(c) for c in v] for v in _HIPS_TRANSLATIONS],'rotations':_rotation_track('Hips')},'joints':{s:{'rotations':_rotation_track(s)} for s in ROTATION_JOINTS}}
def write_compact_animation(path):
    doc=validate_animation(build_animation()); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n',encoding='utf-8')
def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); args=p.parse_args(); write_compact_animation(args.output); return 0
if __name__=='__main__': raise SystemExit(main())
