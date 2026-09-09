import copy
import math
from pathlib import Path

from motion2sheet.motion.humanoid_motion.schema import read_animation, write_animation

ROOT = Path('tests/motion/humanoid_motion/fixtures/dual-wield-crosscut-attack')
KEYPOSE = ROOT / 'keypose_review.json'
OUT = ROOT / 'animation.json'
FPS = 30.0

src = read_animation(KEYPOSE)
assert src['frameCount'] == 8
JOINTS = list(src['joints'])


def qnorm(q):
    n = math.sqrt(sum(v*v for v in q))
    return [v/n for v in q]


def slerp(a, b, t):
    b = list(b)
    dot = sum(x*y for x, y in zip(a, b))
    if dot < 0.0:
        b = [-v for v in b]
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return qnorm([x + (y-x)*t for x, y in zip(a, b)])
    theta = math.acos(dot)
    st = math.sin(theta)
    return qnorm([
        math.sin((1.0-t)*theta)/st*x + math.sin(t*theta)/st*y
        for x, y in zip(a, b)
    ])


def key_pose(index):
    return {
        'hips_t': list(src['hips']['translations'][index]),
        'hips_r': list(src['hips']['rotations'][index]),
        'joints': {j: list(src['joints'][j]['rotations'][index]) for j in JOINTS},
    }


KEYS = [key_pose(i) for i in range(8)]


def clamp01(t):
    return max(0.0, min(1.0, t))


def smooth(t):
    t = clamp01(t)
    return t*t*(3.0 - 2.0*t)


def ease_out(t, power=2.0):
    t = clamp01(t)
    return 1.0 - (1.0-t)**power


def interp_value(a, b, t):
    return [x + (y-x)*t for x, y in zip(a, b)]


def joint_progress(name, t, mode, attack_side=None):
    if mode == 'smooth':
        return smooth(t)
    if mode == 'load':
        # Coil starts in the floor/hips; weapon hands arrive last into chamber.
        if name in ('LeftUpperLeg','LeftLowerLeg','LeftFoot','LeftToe','RightUpperLeg','RightLowerLeg','RightFoot','RightToe'):
            return smooth(clamp01(t*1.18))
        if name in ('Spine','Chest'):
            return smooth(clamp01(t*1.10))
        if name in ('Neck','Head'):
            return smooth(t*0.86)
        if attack_side and name.startswith(attack_side):
            if name.endswith(('LowerArm','Hand')) or any(k in name for k in ('Thumb','Index','Middle','Ring','Pinky')):
                return smooth(t*0.82)
            return smooth(t*0.92)
        return smooth(t)
    if mode == 'attack':
        # Kinetic chain: legs/hips initiate, torso follows, then shoulder, then hand snaps through.
        if name in ('LeftUpperLeg','LeftLowerLeg','LeftFoot','LeftToe','RightUpperLeg','RightLowerLeg','RightFoot','RightToe'):
            return smooth(clamp01(t*1.42))
        if name == 'Spine':
            return smooth(clamp01(t*1.30))
        if name == 'Chest':
            return smooth(clamp01(t*1.22))
        if name in ('Neck','Head'):
            return smooth(clamp01(t*0.88))
        if attack_side and name.startswith(attack_side):
            if name.endswith('Shoulder'):
                return t*t
            if name.endswith('UpperArm'):
                return t**2.25
            if name.endswith('LowerArm'):
                return t**2.7
            if name.endswith('Hand') or any(k in name for k in ('Thumb','Index','Middle','Ring','Pinky')):
                return t**3.1
        return smooth(t)
    if mode == 'follow':
        # Weapon exits quickly while the body loses energy more gradually.
        if attack_side and name.startswith(attack_side):
            if name.endswith(('LowerArm','Hand')) or any(k in name for k in ('Thumb','Index','Middle','Ring','Pinky')):
                return ease_out(t, 3.2)
            return ease_out(t, 2.7)
        if name in ('Spine','Chest'):
            return ease_out(t, 2.15)
        if name in ('Neck','Head'):
            return ease_out(t, 1.65)
        return ease_out(t, 1.9)
    if mode == 'recover':
        return ease_out(t, 2.35)
    raise ValueError(mode)


def kinetic_interp(a, b, t, mode='smooth', attack_side=None):
    # Hips translation/rotation also lead an attack; keep gaze slightly delayed via head/neck rules above.
    if mode == 'attack':
        hips_p = smooth(clamp01(t*1.45))
    elif mode == 'load':
        hips_p = smooth(clamp01(t*1.16))
    elif mode == 'follow':
        hips_p = ease_out(t, 2.1)
    elif mode == 'recover':
        hips_p = ease_out(t, 2.2)
    else:
        hips_p = smooth(t)
    return {
        'hips_t': interp_value(a['hips_t'], b['hips_t'], hips_p),
        'hips_r': slerp(a['hips_r'], b['hips_r'], hips_p),
        'joints': {j: slerp(a['joints'][j], b['joints'][j], joint_progress(j, t, mode, attack_side)) for j in JOINTS},
    }


def impact_accent(impact, follow_pose, attack_side):
    # Body keeps travelling after contact while the attacking hand is almost pinned for one frame.
    out = copy.deepcopy(impact)
    out['hips_t'] = interp_value(impact['hips_t'], follow_pose['hips_t'], 0.16)
    out['hips_r'] = slerp(impact['hips_r'], follow_pose['hips_r'], 0.18)
    for j in JOINTS:
        if j in ('Spine','Chest'):
            t = 0.18
        elif j in ('Neck','Head'):
            t = 0.08
        elif j.startswith(attack_side):
            if j.endswith(('LowerArm','Hand')) or any(k in j for k in ('Thumb','Index','Middle','Ring','Pinky')):
                t = 0.025
            elif j.endswith('UpperArm'):
                t = 0.05
            else:
                t = 0.08
        elif j.startswith('Left') or j.startswith('Right'):
            t = 0.15
        else:
            t = 0.12
        out['joints'][j] = slerp(impact['joints'][j], follow_pose['joints'][j], t)
    return out


# V3 keeps the successful 43-frame / 1.4 s envelope but replaces rigid all-joint interpolation
# with staggered kinetic-chain timing and a non-static impact accent.
frames = [None] * 43


def fill(fa, fb, a, b, mode, attack_side=None):
    span = fb-fa
    for f in range(fa, fb):
        t = (f-fa)/span
        frames[f] = kinetic_interp(a, b, t, mode, attack_side)


fill(0, 7, KEYS[0], KEYS[1], 'load', 'Right')
frames[7] = copy.deepcopy(KEYS[1])
fill(7, 10, KEYS[1], KEYS[2], 'attack', 'Right')
frames[10] = copy.deepcopy(KEYS[2])
frames[11] = impact_accent(KEYS[2], KEYS[3], 'Right')
fill(11, 16, frames[11], KEYS[3], 'follow', 'Right')
frames[16] = copy.deepcopy(KEYS[3])
fill(16, 22, KEYS[3], KEYS[4], 'load', 'Left')
frames[22] = copy.deepcopy(KEYS[4])
fill(22, 25, KEYS[4], KEYS[5], 'attack', 'Left')
frames[25] = copy.deepcopy(KEYS[5])
frames[26] = impact_accent(KEYS[5], KEYS[6], 'Left')
fill(26, 31, frames[26], KEYS[6], 'follow', 'Left')
frames[31] = copy.deepcopy(KEYS[6])
settle = kinetic_interp(KEYS[6], KEYS[7], 0.92, 'recover')
fill(31, 38, KEYS[6], settle, 'recover')
frames[38] = copy.deepcopy(settle)
fill(38, 42, settle, KEYS[7], 'smooth')
frames[42] = copy.deepcopy(KEYS[7])
assert all(p is not None for p in frames)


def lex_negative(q):
    for v in q:
        if abs(v) > 1e-12:
            return v < 0.0
    return False


def continuous(seq):
    out = []
    for q in seq:
        q = qnorm(q)
        if not out and lex_negative(q):
            q = [-v for v in q]
        elif out and sum(a*b for a, b in zip(out[-1], q)) < 0.0:
            q = [-v for v in q]
        out.append(q)
    return out


n = len(frames)
doc = {
    'schema': src['schema'],
    'version': src['version'],
    'id': 'dual-wield-crosscut-attack',
    'canonicalSkeleton': src['canonicalSkeleton'],
    'durationSeconds': (n-1)/FPS,
    'fps': FPS,
    'frameCount': n,
    'loop': False,
    'coordinateSystem': copy.deepcopy(src['coordinateSystem']),
    'quaternionConvention': copy.deepcopy(src['quaternionConvention']),
    'root': {
        'translations': [[0.0, 0.0, 0.0] for _ in frames],
        'rotations': [[1.0, 0.0, 0.0, 0.0] for _ in frames],
    },
    'hips': {
        'translations': [p['hips_t'] for p in frames],
        'rotations': continuous([p['hips_r'] for p in frames]),
    },
    'joints': {
        j: {'rotations': continuous([p['joints'][j] for p in frames])}
        for j in JOINTS
    },
}
write_animation(OUT, doc)
(ROOT / 'timing.txt').write_text(
    '\n'.join([
        '0 ready',
        '7 right_load',
        '10 right_impact',
        '11 right_impact_body_continue_hand_pin',
        '16 right_follow_left_load',
        '22 left_load',
        '25 left_impact',
        '26 left_impact_body_continue_hand_pin',
        '31 left_follow',
        '38 recovery_decelerated_settle',
        '42 recovery',
    ]) + '\n',
    encoding='utf-8',
)
print(f'V3_FINAL_MOTION_PASS {OUT} frames={n} fps={FPS} duration={(n-1)/FPS:.3f}s kineticChain=staggered')
