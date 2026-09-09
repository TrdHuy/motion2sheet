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


def interp(a, b, t):
    return {
        'hips_t': [x + (y-x)*t for x, y in zip(a['hips_t'], b['hips_t'])],
        'hips_r': slerp(a['hips_r'], b['hips_r'], t),
        'joints': {j: slerp(a['joints'][j], b['joints'][j], t) for j in JOINTS},
    }


def smooth(t):
    return t*t*(3.0 - 2.0*t)


def accelerate(t):
    # Slow anticipation, then snap hard into impact.
    return t*t*t


def follow(t):
    # Leave impact fast, then lose energy into follow-through.
    return 1.0 - (1.0-t)**3


# output-frame, key-pose index, easing used to reach the next marker
# Loads are deliberately long; each strike crosses from load to impact in 3 frames.
# Impact is held for one readable frame before a fast follow-through.
MARKERS = [
    (0,  0, 'smooth'),
    (7,  1, 'attack'),
    (10, 2, 'hold'),
    (11, 2, 'follow'),
    (16, 3, 'smooth'),
    (22, 4, 'attack'),
    (25, 5, 'hold'),
    (26, 5, 'follow'),
    (31, 6, 'smooth'),
    (42, 7, 'end'),
]
EASING = {'smooth': smooth, 'attack': accelerate, 'follow': follow}

frames = []
for i, (fa, ka, easing_name) in enumerate(MARKERS[:-1]):
    fb, kb, _ = MARKERS[i+1]
    span = fb-fa
    for f in range(fa, fb):
        if easing_name == 'hold':
            pose = KEYS[ka]
        else:
            raw = (f-fa)/span
            pose = interp(KEYS[ka], KEYS[kb], EASING[easing_name](raw))
        frames.append(copy.deepcopy(pose))
frames.append(copy.deepcopy(KEYS[MARKERS[-1][1]]))
assert len(frames) == 43


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
        '11 right_impact_hold',
        '16 right_follow_left_load',
        '22 left_load',
        '25 left_impact',
        '26 left_impact_hold',
        '31 left_follow',
        '42 recovery',
    ]) + '\n',
    encoding='utf-8',
)
print(f'authored final motion: {OUT} frames={n} fps={FPS} duration={(n-1)/FPS:.3f}s')
