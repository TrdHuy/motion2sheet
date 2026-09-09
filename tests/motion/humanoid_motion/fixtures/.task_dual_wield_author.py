import copy
import math
from pathlib import Path

from motion2sheet.motion.humanoid_motion.schema import read_animation, write_animation

OUT = Path('tests/motion/humanoid_motion/fixtures/dual-wield-crosscut-attack/keypose_review.json')
FPS = 30.0

REFS = {
    'dual': read_animation(Path('sample/humanoid_motion/mixamo/dual-weapon-combo/animation.json')),
    'melee': read_animation(Path('sample/humanoid_motion/mixamo/standing-melee-combo-attack-ver-1/animation.json')),
    'guard': read_animation(Path('sample/humanoid_motion/mixamo/standing-idle-to-fight-idle/animation.json')),
    'club': read_animation(Path('sample/humanoid_motion/mixamo/two-hand-club-combo/animation.json')),
}


def qnorm(q):
    n = math.sqrt(sum(v * v for v in q))
    return [v / n for v in q]


def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [
        aw*bw - ax*bx - ay*by - az*bz,
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
    ]


def qaxis(axis, degrees):
    radians = math.radians(degrees) * 0.5
    s = math.sin(radians)
    return [math.cos(radians), axis[0]*s, axis[1]*s, axis[2]*s]


def qxyz(x=0.0, y=0.0, z=0.0):
    q = [1.0, 0.0, 0.0, 0.0]
    for axis, angle in [((0, 0, 1), z), ((0, 1, 0), y), ((1, 0, 0), x)]:
        q = qmul(q, qaxis(axis, angle))
    return qnorm(q)


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


def frame_pose(doc, frame):
    frame = max(0, min(frame, doc['frameCount'] - 1))
    return {
        'hips_t': list(doc['hips']['translations'][frame]),
        'hips_r': list(doc['hips']['rotations'][frame]),
        'joints': {name: list(track['rotations'][frame]) for name, track in doc['joints'].items()},
    }


def blend_pose(a, b, t):
    names = sorted(set(a['joints']) & set(b['joints']))
    return {
        'hips_t': [x + (y-x)*t for x, y in zip(a['hips_t'], b['hips_t'])],
        'hips_r': slerp(a['hips_r'], b['hips_r'], t),
        'joints': {name: slerp(a['joints'][name], b['joints'][name], t) for name in names},
    }


def scene_offset(pose, joint, xyz):
    pose['joints'][joint] = qnorm(qmul(qxyz(*xyz), pose['joints'][joint]))


def hips_offset(pose, xyz):
    pose['hips_r'] = qnorm(qmul(qxyz(*xyz), pose['hips_r']))


def scale_hips_translation(pose, factor=1.0, add=(0.0, 0.0, 0.0)):
    pose['hips_t'] = [pose['hips_t'][i] * factor + add[i] for i in range(3)]


# Eight deliberately staged silhouettes. Source frames are only anatomical/weight-transfer seeds;
# every key is blended from multiple clips and then selectively re-authored.
# Choreography: ready -> right load -> right cut -> right follow/left load -> left load -> left cut -> left follow -> recovery.
SPECS = [
    # label, sourceA, frameA, sourceB, frameB, blend-to-B
    ('ready',                 'guard', 30, 'dual',   0, 0.35),
    ('right_load',            'dual',  30, 'melee', 38, 0.28),
    ('right_preimpact',       'dual',  40, 'melee', 51, 0.32),
    ('right_follow_left_load','dual',  50, 'melee', 64, 0.30),
    ('left_load',             'dual',  69, 'club',  49, 0.22),
    ('left_preimpact',        'dual',  79, 'melee', 89, 0.30),
    ('left_follow',           'dual',  89, 'melee',102, 0.30),
    ('recovery',              'dual', 109, 'guard', 30, 0.35),
]

poses = []
labels = []
for label, a_name, a_frame, b_name, b_frame, t in SPECS:
    pose = blend_pose(frame_pose(REFS[a_name], a_frame), frame_pose(REFS[b_name], b_frame), t)
    labels.append(label)
    poses.append(pose)

# Re-author the line of action without destroying the source-derived anatomy.
# Offsets are intentionally small and scene-space: the visual gate, not these numbers, is authoritative.
# ready: grounded asymmetry, hands nearer guard rather than celebratory V.
scene_offset(poses[0], 'Chest', (0, 0, -4))
scene_offset(poses[0], 'RightUpperArm', (0, 0, -8))
scene_offset(poses[0], 'LeftUpperArm', (0, 0, 6))
scale_hips_translation(poses[0], 1.05)

# right load: coil right/back, right weapon hand outside silhouette, left hand checking centerline.
hips_offset(poses[1], (0, 0, 8))
scene_offset(poses[1], 'Chest', (0, 0, 10))
scene_offset(poses[1], 'RightShoulder', (0, 0, 8))
scene_offset(poses[1], 'RightUpperArm', (-5, 0, 12))
scene_offset(poses[1], 'LeftUpperArm', (0, 0, -8))
scale_hips_translation(poses[1], 1.20, (0.010, 0.0, -0.004))

# right pre-impact: hip/chest uncoil, attacking arm stays long and crosses body; support side counters.
hips_offset(poses[2], (0, 0, -8))
scene_offset(poses[2], 'Chest', (0, 0, -12))
scene_offset(poses[2], 'RightUpperArm', (0, 0, -10))
scene_offset(poses[2], 'RightLowerArm', (0, 0, 8))
scene_offset(poses[2], 'LeftUpperArm', (0, 0, 7))
scale_hips_translation(poses[2], 1.25, (-0.012, 0.0, -0.006))

# right follow / left load: retain momentum while left shoulder opens for second attack.
hips_offset(poses[3], (0, 0, -5))
scene_offset(poses[3], 'Chest', (0, 0, -7))
scene_offset(poses[3], 'RightUpperArm', (0, 0, -6))
scene_offset(poses[3], 'LeftShoulder', (0, 0, 10))
scene_offset(poses[3], 'LeftUpperArm', (0, 0, 12))
scale_hips_translation(poses[3], 1.20, (-0.008, 0.0, -0.008))

# left load: coil opposite direction and keep right hand as a guard/counterbalance.
hips_offset(poses[4], (0, 0, -10))
scene_offset(poses[4], 'Chest', (0, 0, -12))
scene_offset(poses[4], 'LeftShoulder', (0, 0, -8))
scene_offset(poses[4], 'LeftUpperArm', (0, 0, -10))
scene_offset(poses[4], 'RightUpperArm', (0, 0, 8))
scale_hips_translation(poses[4], 1.25, (-0.010, 0.0, -0.006))

# left pre-impact: reverse uncoil with long left-side attack silhouette.
hips_offset(poses[5], (0, 0, 10))
scene_offset(poses[5], 'Chest', (0, 0, 14))
scene_offset(poses[5], 'LeftUpperArm', (0, 0, 10))
scene_offset(poses[5], 'LeftLowerArm', (0, 0, -7))
scene_offset(poses[5], 'RightUpperArm', (0, 0, -6))
scale_hips_translation(poses[5], 1.30, (0.012, 0.0, -0.007))

# left follow: body continues past the hit instead of stopping at contact.
hips_offset(poses[6], (0, 0, 7))
scene_offset(poses[6], 'Chest', (0, 0, 9))
scene_offset(poses[6], 'LeftUpperArm', (0, 0, 7))
scale_hips_translation(poses[6], 1.25, (0.010, 0.0, -0.006))

# recovery: not perfectly symmetric; settle toward original fight stance.
scene_offset(poses[7], 'Chest', (0, 0, 3))
scene_offset(poses[7], 'RightUpperArm', (0, 0, -4))
scene_offset(poses[7], 'LeftUpperArm', (0, 0, 3))
scale_hips_translation(poses[7], 1.05)

all_joints = sorted(poses[0]['joints'])
for pose in poses:
    if set(pose['joints']) != set(all_joints):
        raise RuntimeError('Reference joint sets differ; key-pose review requires identical canonical tracks')

# Preserve continuous nearest-hemisphere signs frame-to-frame.
def continuous(seq):
    out = []
    for q in seq:
        q = list(q)
        if out and sum(a*b for a, b in zip(out[-1], q)) < 0:
            q = [-v for v in q]
        out.append(qnorm(q))
    return out

root_r = [[1.0, 0.0, 0.0, 0.0] for _ in poses]
root_t = [[0.0, 0.0, 0.0] for _ in poses]
hips_r = continuous([p['hips_r'] for p in poses])
joint_tracks = {j: continuous([p['joints'][j] for p in poses]) for j in all_joints}

doc = {
    'schema': 'motion2sheet.humanoid-motion.animation',
    'version': 1,
    'id': 'dual-wield-crosscut-attack-keypose-review',
    'canonicalSkeleton': 'humanoid_v1',
    'durationSeconds': (len(poses)-1)/FPS,
    'fps': FPS,
    'frameCount': len(poses),
    'loop': False,
    'coordinateSystem': copy.deepcopy(REFS['dual']['coordinateSystem']),
    'quaternionConvention': copy.deepcopy(REFS['dual']['quaternionConvention']),
    'root': {'translations': root_t, 'rotations': root_r},
    'hips': {'translations': [p['hips_t'] for p in poses], 'rotations': hips_r},
    'joints': {j: {'rotations': joint_tracks[j]} for j in all_joints},
}

OUT.parent.mkdir(parents=True, exist_ok=True)
write_animation(OUT, doc)
(OUT.parent / 'keypose_labels.txt').write_text('\n'.join(f'{i}: {label}' for i, label in enumerate(labels)) + '\n', encoding='utf-8')
print(f'authored key-pose review: {OUT} frames={len(poses)} labels={labels}')
