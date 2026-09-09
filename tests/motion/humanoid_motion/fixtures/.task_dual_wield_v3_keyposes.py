import copy
import math
from pathlib import Path

from motion2sheet.motion.humanoid_motion.schema import read_animation, write_animation

ROOT = Path('tests/motion/humanoid_motion/fixtures/dual-wield-crosscut-attack')
PATH = ROOT / 'keypose_review.json'

doc = read_animation(PATH)
assert doc['frameCount'] == 8


def qnorm(q):
    n = math.sqrt(sum(v * v for v in q))
    return [v / n for v in q]


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


def continuous(seq):
    out = []
    for q in seq:
        q = qnorm(list(q))
        if not out:
            for v in q:
                if abs(v) > 1e-12:
                    if v < 0.0:
                        q = [-x for x in q]
                    break
        elif sum(a*b for a, b in zip(out[-1], q)) < 0.0:
            q = [-x for x in q]
        out.append(q)
    return out


# Keep the successful V2 attack silhouettes, but stop the non-attacking arm from
# opening into a near-horizontal T shape at the second impact. Blend that support
# chain toward the grounded ready guard instead of inventing new Euler angles.
ready = 0
left_impact = 5
support_names = ['RightShoulder', 'RightUpperArm', 'RightLowerArm', 'RightHand']
support_names += [name for name in doc['joints'] if name.startswith('Right') and any(
    token in name for token in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
)]
for name in support_names:
    track = doc['joints'][name]['rotations']
    track[left_impact] = slerp(track[left_impact], track[ready], 0.68)

# First impact already reads well; only bring its checking hand slightly nearer the
# centerline so the two strikes share the same dual-wield guard logic.
right_impact = 2
for name in ['LeftShoulder', 'LeftUpperArm', 'LeftLowerArm', 'LeftHand']:
    track = doc['joints'][name]['rotations']
    track[right_impact] = slerp(track[right_impact], track[ready], 0.22)

# Re-canonicalize quaternion signs after the local key-pose edits.
doc['hips']['rotations'] = continuous(doc['hips']['rotations'])
for name in doc['joints']:
    doc['joints'][name]['rotations'] = continuous(doc['joints'][name]['rotations'])

write_animation(PATH, doc)
print('V3_KEYPOSE_REFINEMENT_PASS support-arm guard tightened at both impacts')
