from __future__ import annotations
import math
import bpy
from mathutils import Quaternion, Vector


def apply_animation(arm,animation,scales):
    names=set()
    for pb in arm.pose.bones: pb.rotation_mode='QUATERNION'
    for row in animation['frames']:
        frame=int(row['frame'])
        for name,tr in row['bones'].items():
            pb=arm.pose.bones.get(name)
            if pb is None: raise RuntimeError(f'animation bone missing from armature: {name}')
            names.add(name); factor=float(scales.get(name,1)); pb.location=Vector(tuple(float(v)*factor for v in tr['translation'])); pb.rotation_quaternion=Quaternion(tuple(float(v) for v in tr['rotationQuaternion'])); pb.scale=Vector(tuple(float(v) for v in tr['scale']))
            pb.keyframe_insert('location',frame=frame,group=name); pb.keyframe_insert('rotation_quaternion',frame=frame,group=name); pb.keyframe_insert('scale',frame=frame,group=name)
    return names


def world_point(arm,p): return arm.matrix_world @ p
def bone_dir(arm,name):
    pb=arm.pose.bones[name]; return (world_point(arm,pb.tail)-world_point(arm,pb.head)).normalized()
def angle(a,b): return math.degrees(a.angle(b)) if a.length and b.length else 0.0
def bend(arm,a,b): return angle(bone_dir(arm,a),bone_dir(arm,b))


def setup_scene(request,char_arm):
    scene=bpy.context.scene; canvas=request['canvas']; scene.render.engine='BLENDER_EEVEE_NEXT'; scene.render.resolution_x=int(canvas[0]); scene.render.resolution_y=int(canvas[1]); scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGBA'; scene.render.image_settings.color_depth='8'; scene.render.film_transparent=bool(request['background']['transparent']); scene.world.color=tuple(request['background']['rgba'][:3])
    data=bpy.data.cameras.new('RenderCamera'); camera=bpy.data.objects.new('RenderCamera',data); bpy.context.collection.objects.link(camera); scene.camera=camera; data.type='ORTHO'; data.ortho_scale=float(request['camera']['orthoScale'])
    base_loc=Vector(tuple(request['camera']['location'])); base_target=Vector(tuple(request['camera']['target'])); root=request['compatibility']['rootBone']; first=min(int(x['frame']) for x in request['animationFrames']); scene.frame_set(first); base_root=world_point(char_arm,char_arm.pose.bones[root].head)
    for frame in sorted(int(x['frame']) for x in request['animationFrames']):
        scene.frame_set(frame); delta=world_point(char_arm,char_arm.pose.bones[root].head)-base_root if request['camera'].get('followRoot') else Vector((0,0,0)); loc=base_loc+delta; target=base_target+delta; camera.location=loc; camera.rotation_euler=(target-loc).to_track_quat('-Z','Y').to_euler(); camera.keyframe_insert('location',frame=frame); camera.keyframe_insert('rotation_euler',frame=frame)
    for name,energy,location,size in [('Key',700,(3,-4,6),5),('Fill',350,(-3,-2,3),4)]:
        light=bpy.data.lights.new(name,'AREA'); light.energy=energy; light.size=size; obj=bpy.data.objects.new(name,light); bpy.context.collection.objects.link(obj); obj.location=location


def diagnostics(source_arm,char_arm,animation,compatibility,source_names,char_names):
    semantics={'leftUpperArm':'mixamorig:LeftArm','leftForeArm':'mixamorig:LeftForeArm','rightUpperArm':'mixamorig:RightArm','rightForeArm':'mixamorig:RightForeArm','leftThigh':'mixamorig:LeftUpLeg','leftShin':'mixamorig:LeftLeg','rightThigh':'mixamorig:RightUpLeg','rightShin':'mixamorig:RightLeg'}
    max_dir=max_bend=max_local=max_root=0.0; worst_dir=worst_bend=worst_local=worst_root=None
    by_frame={int(f['frame']):f for f in animation['frames']}; root=compatibility['rootBone']; first=last=min(by_frame),max(by_frame); source_root=[]; char_root=[]
    for frame in sorted(by_frame):
        bpy.context.scene.frame_set(frame)
        for semantic,bone in semantics.items():
            err=angle(bone_dir(source_arm,bone),bone_dir(char_arm,bone))
            if err>max_dir: max_dir=err; worst_dir={'frame':frame,'semantic':semantic,'bone':bone}
        for label,a,b in [('leftElbow','mixamorig:LeftArm','mixamorig:LeftForeArm'),('rightElbow','mixamorig:RightArm','mixamorig:RightForeArm'),('leftKnee','mixamorig:LeftUpLeg','mixamorig:LeftLeg'),('rightKnee','mixamorig:RightUpLeg','mixamorig:RightLeg')]:
            err=abs(bend(source_arm,a,b)-bend(char_arm,a,b))
            if err>max_bend: max_bend=err; worst_bend={'frame':frame,'semantic':label}
        for name,tr in by_frame[frame]['bones'].items():
            expected=Quaternion(tuple(float(v) for v in tr['rotationQuaternion'])); actual=char_arm.pose.bones[name].rotation_quaternion.normalized(); err=math.degrees(expected.rotation_difference(actual).angle)
            if err>max_local: max_local=err; worst_local={'frame':frame,'bone':name}
        if frame in (first,last): source_root.append(world_point(source_arm,source_arm.pose.bones[root].head)); char_root.append(world_point(char_arm,char_arm.pose.bones[root].head))
    if len(source_root)==2:
        sd=source_root[1]-source_root[0]; cd=char_root[1]-char_root[0]
        if sd.length>1e-9 and cd.length>1e-9: max_root=angle(sd,cd); worst_root={'firstFrame':first,'lastFrame':last}
    fingers=[n for n in source_arm.pose.bones.keys() if ('Hand' in n and any(c.isdigit() for c in n)) or 'Toe' in n]
    names_ok=source_names==char_names==set(by_frame[first]['bones'])
    passed=max_dir<=.001 and max_bend<=.001 and max_local<=.0001 and max_root<=.001 and names_ok
    return {'pass':passed,'appliedBoneCount':len(char_names),'fingerToeBoneCount':len(fingers),'maxSemanticDirectionErrorDegrees':max_dir,'worstSemanticDirection':worst_dir,'maxJointBendErrorDegrees':max_bend,'worstJointBend':worst_bend,'maxLocalRotationErrorDegrees':max_local,'worstLocalRotation':worst_local,'leftRightIdentityPass':names_ok,'rootMotion':{'policy':compatibility['rootTranslationPolicy'],'scale':compatibility['rootTranslationScale'],'directionPreserved':max_root<=.001,'directionErrorDegrees':max_root,'worst':worst_root}}
