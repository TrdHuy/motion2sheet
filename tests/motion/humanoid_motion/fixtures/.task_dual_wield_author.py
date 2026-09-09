import json, math
from pathlib import Path

N=61
FPS=30.0
OUT=Path('tests/motion/humanoid_motion/fixtures/dual-wield-crosscut-attack/animation.json')

def qmul(a,b):
    aw,ax,ay,az=a; bw,bx,by,bz=b
    return [aw*bw-ax*bx-ay*by-az*bz,aw*bx+ax*bw+ay*bz-az*by,aw*by-ax*bz+ay*bw+az*bx,aw*bz+ax*by-ay*bx+az*bw]

def norm(q):
    n=math.sqrt(sum(v*v for v in q)); return [v/n for v in q]

def qaxis(axis,deg):
    r=math.radians(deg)/2; s=math.sin(r); c=math.cos(r); x,y,z=axis
    return [c,x*s,y*s,z*s]

def qxyz(x=0,y=0,z=0):
    q=[1.,0.,0.,0.]
    for axis,deg in [((0,0,1),z),((0,1,0),y),((1,0,0),x)]: q=qmul(q,qaxis(axis,deg))
    return norm(q)

def slerp(a,b,t):
    d=sum(x*y for x,y in zip(a,b))
    if d<0: b=[-x for x in b]; d=-d
    d=max(-1,min(1,d))
    if d>.9995: return norm([x+t*(y-x) for x,y in zip(a,b)])
    th=math.acos(d); s=math.sin(th)
    return norm([(math.sin((1-t)*th)/s)*x+(math.sin(t*th)/s)*y for x,y in zip(a,b)])

def ease(t): return t*t*(3-2*t)

def qtrack(keys):
    ks=sorted(keys.items()); out=[]
    for f in range(N):
        if f<=ks[0][0]: q=ks[0][1]
        elif f>=ks[-1][0]: q=ks[-1][1]
        else:
            for (fa,qa),(fb,qb) in zip(ks,ks[1:]):
                if fa<=f<=fb: q=slerp(qa,qb,ease((f-fa)/(fb-fa))); break
        if out and sum(a*b for a,b in zip(out[-1],q))<0: q=[-v for v in q]
        out.append(q)
    return out

def vtrack(keys):
    ks=sorted(keys.items()); out=[]
    for f in range(N):
        if f<=ks[0][0]: v=ks[0][1]
        elif f>=ks[-1][0]: v=ks[-1][1]
        else:
            for (fa,va),(fb,vb) in zip(ks,ks[1:]):
                if fa<=f<=fb:
                    t=ease((f-fa)/(fb-fa)); v=[a+(b-a)*t for a,b in zip(va,vb)]; break
        out.append(v)
    return out

KF=[0,8,14,20,25,31,36,43,50,60]
I=[1.,0.,0.,0.]
E={
'Hips':{0:(4,0,0),8:(5,-1,2),14:(9,5,18),20:(11,-3,-12),25:(8,-3,-20),31:(9,-4,-16),36:(12,3,13),43:(9,4,23),50:(6,1,9),60:(4,0,0)},
'Spine':{0:(3,0,0),8:(4,0,1),14:(7,2,14),20:(9,-2,-10),25:(7,-2,-15),31:(7,-2,-13),36:(10,2,10),43:(7,2,17),50:(5,1,7),60:(3,0,0)},
'Chest':{0:(2,0,0),8:(3,0,1),14:(8,3,27),20:(11,-3,-24),25:(8,-3,-31),31:(8,-2,-27),36:(12,3,19),43:(9,4,31),50:(5,1,12),60:(2,0,0)},
'Neck':{0:(0,0,0),8:(0,0,0),14:(-2,0,-9),20:(-2,0,8),25:(-1,0,10),31:(-2,0,8),36:(-2,0,-7),43:(-1,0,-10),50:(0,0,-4),60:(0,0,0)},
'Head':{0:(0,0,0),8:(0,0,0),14:(-1,0,-13),20:(-1,0,11),25:(0,0,13),31:(-1,0,11),36:(-1,0,-9),43:(0,0,-14),50:(0,0,-5),60:(0,0,0)},
'LeftShoulder':{0:(0,0,3),8:(0,0,4),14:(2,0,23),20:(2,0,-18),25:(1,0,-25),31:(1,0,-22),36:(2,0,17),43:(1,0,27),50:(0,0,10),60:(0,0,3)},
'RightShoulder':{0:(0,0,-2),8:(0,0,-2),14:(2,0,29),20:(2,0,-20),25:(1,0,-27),31:(1,0,-23),36:(2,0,15),43:(1,0,25),50:(0,0,8),60:(0,0,-2)},
'RightUpperArm':{0:(0,58,-23),8:(0,55,-25),14:(0,-48,34),20:(0,28,-104),25:(0,38,-125),31:(0,42,-72),36:(0,35,-98),43:(0,50,-75),50:(0,57,-38),60:(0,58,-23)},
'RightLowerArm':{0:(0,36,-58),8:(0,34,-62),14:(0,-68,47),20:(0,20,-137),25:(0,28,-150),31:(0,30,-94),36:(0,30,-113),43:(0,42,-92),50:(0,40,-66),60:(0,36,-58)},
'RightHand':{0:(-4,28,-62),8:(-3,27,-66),14:(-5,-58,53),20:(6,18,-146),25:(9,24,-157),31:(3,25,-100),36:(1,25,-120),43:(0,36,-98),50:(-2,32,-72),60:(-4,28,-62)},
'LeftUpperArm':{0:(0,-50,31),8:(0,-48,34),14:(0,-34,49),20:(0,-54,118),25:(0,-52,101),31:(0,-66,-29),36:(0,24,108),43:(0,40,138),50:(0,-26,76),60:(0,-50,31)},
'LeftLowerArm':{0:(0,-29,72),8:(0,-27,76),14:(0,-14,90),20:(0,-42,132),25:(0,-38,115),31:(0,-58,-42),36:(0,35,142),43:(0,48,151),50:(0,-16,94),60:(0,-29,72)},
'LeftHand':{0:(4,-23,78),8:(3,-22,81),14:(3,-10,94),20:(-2,-35,139),25:(-4,-30,121),31:(5,-52,-49),36:(-6,42,148),43:(-9,55,158),50:(2,-12,100),60:(4,-23,78)},
'LeftUpperLeg':{0:(-3,-3,0),8:(-3,-3,0),14:(-5,-4,1),20:(-6,-3,-1),25:(-5,-2,-1),31:(2,-4,-1),36:(-5,-3,1),43:(-4,-2,1),50:(-3,-3,0),60:(-3,-3,0)},
'LeftLowerLeg':{0:(5,0,0),8:(5,0,0),14:(7,0,0),20:(8,0,0),25:(7,0,0),31:(-2,0,0),36:(7,0,0),43:(6,0,0),50:(5,0,0),60:(5,0,0)},
'RightUpperLeg':{0:(-4,3,0),8:(-4,3,0),14:(3,4,-1),20:(-5,3,1),25:(-4,2,1),31:(-6,4,1),36:(-6,3,-1),43:(-5,2,-1),50:(-4,3,0),60:(-4,3,0)},
'RightLowerLeg':{0:(6,0,0),8:(6,0,0),14:(-3,0,0),20:(7,0,0),25:(6,0,0),31:(8,0,0),36:(8,0,0),43:(7,0,0),50:(6,0,0),60:(6,0,0)} }
for j in ('LeftFoot','LeftToe','RightFoot','RightToe'): E[j]={f:(0,0,0) for f in KF}
hips_t={0:[0,0,0],8:[.004,0,-.002],14:[.024,0,-.015],20:[-.014,0,-.008],25:[-.022,0,-.006],31:[-.022,0,-.013],36:[.014,0,-.008],43:[.022,0,-.005],50:[.008,0,-.002],60:[0,0,0]}
tracks={j:qtrack({f:qxyz(*v) for f,v in k.items()}) for j,k in E.items() if j!='Hips'}
hips_rot=qtrack({f:qxyz(*v) for f,v in E['Hips'].items()})

fingers=[]
for side in ('Left','Right'):
    fingers += [f'{side}ThumbMetacarpal',f'{side}ThumbProximal',f'{side}ThumbDistal',f'{side}IndexProximal',f'{side}IndexIntermediate',f'{side}IndexDistal',f'{side}MiddleProximal',f'{side}MiddleIntermediate',f'{side}MiddleDistal',f'{side}RingProximal',f'{side}RingIntermediate',f'{side}RingDistal',f'{side}PinkyProximal',f'{side}PinkyIntermediate',f'{side}PinkyDistal']

def grip(name):
    side='Left' if name.startswith('Left') else 'Right'; s=-1 if side=='Left' else 1
    if 'ThumbMetacarpal' in name: return qxyz(0,s*28,-s*22)
    if 'ThumbProximal' in name: return qxyz(0,s*42,-s*28)
    if 'ThumbDistal' in name: return qxyz(0,s*54,-s*24)
    a=58 if 'Proximal' in name else 76 if 'Intermediate' in name else 84
    fan=3 if 'Index' in name else -2 if 'Ring' in name else -5 if 'Pinky' in name else 0
    return qxyz(0,s*a,s*fan)
for name in fingers:
    hand='LeftHand' if name.startswith('Left') else 'RightHand'; g=grip(name); seq=[]
    for hq in tracks[hand]:
        q=norm(qmul(hq,g))
        if seq and sum(a*b for a,b in zip(seq[-1],q))<0: q=[-v for v in q]
        seq.append(q)
    tracks[name]=seq

core=['Spine','Chest','Neck','Head','LeftShoulder','LeftUpperArm','LeftLowerArm','LeftHand','RightShoulder','RightUpperArm','RightLowerArm','RightHand','LeftUpperLeg','LeftLowerLeg','LeftFoot','LeftToe','RightUpperLeg','RightLowerLeg','RightFoot','RightToe']
doc={'schema':'motion2sheet.humanoid-motion.animation','version':1,'id':'dual-wield-crosscut-attack','canonicalSkeleton':'humanoid_v1','durationSeconds':2.0,'fps':FPS,'frameCount':N,'loop':False,'coordinateSystem':{'handedness':'right-handed','rightAxis':'+X','forwardAxis':'-Y','upAxis':'+Z','translationUnit':'mean-leg-length'},'quaternionConvention':{'componentOrder':'wxyz','deltaSpace':'canonical-scene-rest-relative-left-delta','signPolicy':'continuous-nearest-hemisphere'},'root':{'translations':[[0.,0.,0.] for _ in range(N)],'rotations':[I[:] for _ in range(N)]},'hips':{'translations':vtrack(hips_t),'rotations':hips_rot},'joints':{j:{'rotations':tracks[j]} for j in core+fingers}}
OUT.parent.mkdir(parents=True,exist_ok=True)
from motion2sheet.motion.humanoid_motion.schema import write_animation
write_animation(OUT,doc)
print(f'authored {OUT} frames={N} fps={FPS} fingers={len(fingers)}')
