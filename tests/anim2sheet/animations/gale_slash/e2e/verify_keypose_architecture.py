from __future__ import annotations
import json, sys
from pathlib import Path
CORE_FRAMES={1,6,7,8}; root=Path(sys.argv[1]); debug=json.loads((root/'motion_debug.json').read_text()); samples=debug.get('samples',[]); frames=[int(r['frame']) for r in samples]
if not frames or frames!=sorted(set(frames)): raise SystemExit(f'review frames must be sorted/unique, got {frames}')
if CORE_FRAMES-set(frames): raise SystemExit(f'review lost frozen core frames: missing={sorted(CORE_FRAMES-set(frames))}')
if debug.get('armControl')!='deterministic_joint_fk': raise SystemExit('fast review must use deterministic_joint_fk arms')
by={int(r['frame']):r for r in samples}; checks={}; leg=json.loads((root/'leg_ik_debug.json').read_text()); leg_rows=leg.get('framesData',[])
if [int(r['frame']) for r in leg_rows]!=frames: raise SystemExit('leg IK diagnostic frames do not match fast-review frames')
knees={}
for fr in leg_rows:
    f=int(fr['frame']); knees[str(f)]={}
    for side in ('left','right'):
        row=fr.get('legs',{}).get(side)
        if not row: raise SystemExit(f'F{f} {side} knee authority data is missing')
        knees[str(f)][side]={k:row[k] for k in ('hip','knee','ankle','kneeGuide','evaluatedBendDirection','guideBendDirection','alignmentCos','match')}
        if not bool(row['match']) or float(row['alignmentCos'])<=0: raise SystemExit(f"F{f} {side} knee bends opposite authored guide: alignment={float(row['alignmentCos']):.6f}")
checks['kneeGuideAuthority']=knees; checks['legIkPoleAnglesDeg']={s:float(leg['rigSetup'][s]['ik']['poleAngleDeg']) for s in ('left','right')}
max_err=max(float(r['maxArmJointError']) for r in samples); checks['maxArmJointError']=max_err
if max_err>0.008: raise SystemExit(f'authored arm joints drifted after evaluation: {max_err:.4f}m')
max_primary=max(float(r['weaponGripContract']['primaryLeftWristError']) for r in samples); max_axis=max(float(r['weaponGripContract']['rightWristAxisError']) for r in samples); spans=[float(r['weaponGripContract']['rightWristAlongGrip']) for r in samples]
checks.update(maxPrimaryGripError=max_primary,maxSecondaryAxisError=max_axis,gripSpans=spans)
if max_primary>0.008 or max_axis>0.008: raise SystemExit('weapon is not deterministically bound to the authored hand sockets')
if not all(0.10<=v<=0.15 for v in spans): raise SystemExit(f'two-hand grip span is unstable: {spans}')
f1=by[1]['joints']; ls,le=f1['leftShoulder'],f1['leftElbow']; rs,re=f1['rightShoulder'],f1['rightElbow']; lw=f1['leftWrist']
if not (le[0]<ls[0] and re[0]>rs[0]): raise SystemExit('F1 elbow topology crosses the torso instead of staying anatomical')
if le[2]>=ls[2] or re[2]>=rs[2]: raise SystemExit('F1 elbows form a chicken-wing/high-guard topology')
if float(lw[0])>0.02: raise SystemExit(f'F1 left forearm crosses too far through body centerline: wrist x={lw[0]:.3f}')
f1a=[float(by[1]['leftElbowAngleDeg']),float(by[1]['rightElbowAngleDeg'])]; checks['f1ElbowAngles']=f1a; checks['f1LeftWristX']=float(lw[0])
if not all(55<=v<=125 for v in f1a): raise SystemExit(f'F1 elbow bend is anatomically implausible: {f1a}')
if float(by[1]['rootTranslation'][2])>-0.05: raise SystemExit('F1 ready stance is not low enough for this key-pose proof')
def dx(f): return float(by[f]['swordTip'][0])-float(by[f]['swordGrip'][0])
f6dx,f8dx=dx(6),dx(8); f6len=float(by[6]['projectedSwordLengthXZ']); f7len=float(by[7]['projectedSwordLengthXZ']); f8len=float(by[8]['projectedSwordLengthXZ']); checks['strike']={'f6Dx':f6dx,'f7ProjectedLengthXZ':f7len,'f8Dx':f8dx}
if f6dx<0.8: raise SystemExit(f'F6 sword does not clearly enter screen-right: dx={f6dx:.3f}')
if f8dx>-0.8: raise SystemExit(f'F8 sword does not clearly exit screen-left: dx={f8dx:.3f}')
if not 0.12<=f7len<=0.35: raise SystemExit(f'F7 depth pose has unreadable projection: {f7len:.3f}m')
if not (f7len<f6len*0.35 and f7len<f8len*0.35): raise SystemExit('F7 does not create a clear foreshortened impact transition')
exts={}; inds={}; elbows={}
for f in (6,7,8):
    l=float(by[f]['leftArmExtension']); r=float(by[f]['rightArmExtension']); avg=(l+r)/2; exts[str(f)]=avg; inds[str(f)]={'left':l,'right':r}
    if avg<0.30 or min(l,r)<0.28: raise SystemExit(f'F{f} arm posture collapsed: left={l:.3f}, right={r:.3f}')
    la=float(by[f]['leftElbowAngleDeg']); ra=float(by[f]['rightElbowAngleDeg']); elbows[str(f)]={'left':la,'right':ra}
    if max(la,ra)>145: raise SystemExit(f'F{f} elbow is too close to lock-out: left={la:.1f}, right={ra:.1f}')
checks['strikeArmExtension']=exts; checks['individualArmExtension']=inds; checks['strikeElbowAngles']=elbows
if float(by[8]['rightArmExtension'])<0.30: raise SystemExit(f"F8 right arm collapses during strike exit: {by[8]['rightArmExtension']:.3f}")
stance={str(f):float(by[f]['stanceWidth']) for f in frames}; checks['stanceWidth']=stance
if min(stance.values())<0.25: raise SystemExit(f'key-pose stance collapsed: {stance}')
sk={}
for f in (6,7,8):
    vals=[float(by[f]['leftKneeAngleDeg']),float(by[f]['rightKneeAngleDeg'])]; sk[str(f)]=vals
    if min(vals)>160: raise SystemExit(f'F{f} strike stance is too straight: {vals}')
checks['strikeKneeAngles']=sk; result={'status':'pass','mode':'fast-keypose-review','frames':frames,'checks':checks}; (root/'semantic_checks.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
