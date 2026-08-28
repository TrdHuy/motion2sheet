"""Blender-native Gale Slash POC using physically correct horizontal sword yaw."""
from __future__ import annotations

import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector


def argv(): return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def add_bone(eb,name,head,tail,parent=None):
    b=eb.new(name); b.head=head; b.tail=tail
    if parent: b.parent=parent
    return b
def material(name,color,metallic=0.0):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1.0); m.use_nodes=True
    bsdf=m.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Base Color"].default_value=(*color,1.0); bsdf.inputs["Roughness"].default_value=0.55; bsdf.inputs["Metallic"].default_value=metallic
    return m
def weighted_cylinder(arm,name,bone_name,head,tail,radius,mat):
    a,b=Vector(head),Vector(tail); d=b-a
    bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=radius,depth=d.length,location=(a+b)*0.5)
    o=bpy.context.object; o.name=name; o.rotation_mode="QUATERNION"; o.rotation_quaternion=Vector((0,0,1)).rotation_difference(d.normalized()); bpy.ops.object.transform_apply(location=True,rotation=True,scale=True); o.data.materials.append(mat)
    vg=o.vertex_groups.new(name=bone_name); vg.add(range(len(o.data.vertices)),1.0,"REPLACE"); mod=o.modifiers.new("Armature","ARMATURE"); mod.object=arm
def weighted_sphere(arm,name,bone_name,center,radius,mat):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=radius,location=center); o=bpy.context.object; o.name=name; bpy.ops.object.transform_apply(location=True,rotation=True,scale=True); o.data.materials.append(mat)
    vg=o.vertex_groups.new(name=bone_name); vg.add(range(len(o.data.vertices)),1.0,"REPLACE"); mod=o.modifiers.new("Armature","ARMATURE"); mod.object=arm
def controller_cylinder(parent,name,z0,z1,radius,mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=radius,depth=z1-z0,location=(0,0,(z0+z1)*0.5)); o=bpy.context.object; o.name=name; o.data.materials.append(mat); o.parent=parent


def build_rig():
    data=bpy.data.armatures.new("GameHumanoidV1"); arm=bpy.data.objects.new("GameHumanoidV1",data); bpy.context.collection.objects.link(arm); bpy.context.view_layer.objects.active=arm; arm.select_set(True); bpy.ops.object.mode_set(mode="EDIT"); eb=data.edit_bones
    hips=add_bone(eb,"Hips",(0,0,0.98),(0,0,1.18)); spine=add_bone(eb,"Spine",(0,0,1.18),(0,0,1.55),hips); neck=add_bone(eb,"Neck",(0,0,1.55),(0,0,1.70),spine); add_bone(eb,"Head",(0,0,1.70),(0,0,1.93),neck)
    ls=add_bone(eb,"LeftShoulder",(0,0,1.53),(-0.18,0,1.53),spine); lua=add_bone(eb,"LeftUpperArm",(-0.18,0,1.53),(-0.46,0,1.42),ls); lfa=add_bone(eb,"LeftForeArm",(-0.46,0,1.42),(-0.68,0,1.25),lua); add_bone(eb,"LeftHand",(-0.68,0,1.25),(-0.77,0,1.18),lfa)
    rs=add_bone(eb,"RightShoulder",(0,0,1.53),(0.18,0,1.53),spine); rua=add_bone(eb,"RightUpperArm",(0.18,0,1.53),(0.46,0,1.42),rs); rfa=add_bone(eb,"RightForeArm",(0.46,0,1.42),(0.68,0,1.25),rua); add_bone(eb,"RightHand",(0.68,0,1.25),(0.77,0,1.18),rfa)
    lt=add_bone(eb,"LeftUpLeg",(-0.28,0,0.98),(-0.30,0,0.56),hips); ll=add_bone(eb,"LeftLeg",(-0.30,0,0.56),(-0.30,0,0.15),lt); add_bone(eb,"LeftFoot",(-0.30,0,0.15),(-0.30,-0.25,0.08),ll)
    rt=add_bone(eb,"RightUpLeg",(0.28,0,0.98),(0.30,0,0.56),hips); rl=add_bone(eb,"RightLeg",(0.30,0,0.56),(0.30,0,0.15),rt); add_bone(eb,"RightFoot",(0.30,0,0.15),(0.30,-0.25,0.08),rl)
    bpy.ops.object.mode_set(mode="POSE")
    for b in arm.pose.bones: b.rotation_mode="XYZ"
    bpy.ops.object.mode_set(mode="OBJECT"); return arm


def build_character(arm):
    cloth=material("Cloth",(0.07,0.15,0.30)); skin=material("Skin",(0.72,0.48,0.32)); boots=material("Boots",(0.055,0.04,0.035)); bones=arm.data.bones
    for name,r,mat in [("Spine",0.18,cloth),("LeftUpperArm",0.08,cloth),("LeftForeArm",0.07,skin),("RightUpperArm",0.08,cloth),("RightForeArm",0.07,skin),("LeftUpLeg",0.11,cloth),("LeftLeg",0.09,boots),("RightUpLeg",0.11,cloth),("RightLeg",0.09,boots),("LeftFoot",0.08,boots),("RightFoot",0.08,boots)]:
        b=bones[name]; weighted_cylinder(arm,"Body_"+name,name,b.head_local,b.tail_local,r,mat)
    weighted_sphere(arm,"HeadMesh","Head",(0,0,1.82),0.15,skin); weighted_sphere(arm,"PelvisMesh","Hips",(0,0,1.07),0.20,cloth)
    for name,center,r,mat in [("LeftUpperArm",(-0.18,0,1.53),0.085,skin),("RightUpperArm",(0.18,0,1.53),0.085,skin),("LeftForeArm",(-0.46,0,1.42),0.075,skin),("RightForeArm",(0.46,0,1.42),0.075,skin),("LeftHand",(-0.725,0,1.215),0.075,skin),("RightHand",(0.725,0,1.215),0.075,skin),("LeftLeg",(-0.30,0,0.56),0.095,cloth),("RightLeg",(0.30,0,0.56),0.095,cloth)]: weighted_sphere(arm,"Joint_"+name,name,center,r,mat)


def build_sword_and_right_ik(arm):
    steel=material("Steel",(0.55,0.62,0.70),0.75); grip=material("Grip",(0.12,0.055,0.025),0.1)
    ctrl=bpy.data.objects.new("SwordController",None); bpy.context.collection.objects.link(ctrl); ctrl.rotation_mode="XYZ"; controller_cylinder(ctrl,"SwordGrip",-0.07,0.25,0.045,grip); controller_cylinder(ctrl,"SwordBlade",0.24,1.20,0.035,steel)
    target=bpy.data.objects.new("RightGripTarget",None); pole=bpy.data.objects.new("RightElbowPole",None); bpy.context.collection.objects.link(target); bpy.context.collection.objects.link(pole); target.parent=ctrl; target.location=(0,0,0.03); pole.parent=arm; pole.location=(0.70,-1.0,1.28)
    ik=arm.pose.bones["RightHand"].constraints.new("IK"); ik.target=target; ik.pole_target=pole; ik.chain_count=3; ik.iterations=64; ik.pole_angle=math.radians(-90)
    return ctrl


def key_rotation(arm,name,frame,y_deg=0.0,z_deg=0.0):
    b=arm.pose.bones[name]; b.rotation_euler.y=math.radians(y_deg); b.rotation_euler.z=math.radians(z_deg); b.keyframe_insert(data_path="rotation_euler",frame=frame)
def key_body(arm,frame,x,z,hip_twist,spine_twist,head_twist,lt,ls,rt,rs,lua,lfa):
    bpy.context.scene.frame_set(frame); arm.location=(x,0,z); arm.keyframe_insert(data_path="location",frame=frame)
    key_rotation(arm,"Hips",frame,z_deg=hip_twist); key_rotation(arm,"Spine",frame,z_deg=spine_twist); key_rotation(arm,"Head",frame,z_deg=head_twist)
    for name,deg in {"LeftUpLeg":lt,"LeftLeg":ls,"RightUpLeg":rt,"RightLeg":rs,"LeftUpperArm":lua,"LeftForeArm":lfa}.items(): key_rotation(arm,name,frame,y_deg=deg)
def key_sword(ctrl,frame,x,z,yaw_deg):
    # Local blade starts on +Z. Y=90 lays it horizontally; Z yaw then performs a true chest-level horizontal sweep in X-Y.
    bpy.context.scene.frame_set(frame); ctrl.location=(x,-0.04,z); ctrl.rotation_euler=(0,math.radians(90),math.radians(yaw_deg)); ctrl.keyframe_insert(data_path="location",frame=frame); ctrl.keyframe_insert(data_path="rotation_euler",frame=frame)


def animate(arm,sword,frames):
    bpy.context.scene.frame_start=1; bpy.context.scene.frame_end=frames
    # Hips lead, chest follows, head counter-rotates to keep the target in view. Legs provide a visible crouch/weight transfer.
    body=[
        (1,0.00,0.00,0,0,0,-7,10,7,-10,10,-16),
        (3,0.00,-0.04,-8,-14,6,-12,20,12,-16,8,-12),
        (4,0.00,-0.09,-18,-28,12,-18,30,18,-24,5,-8),
        (6,0.08,-0.07,-8,-16,8,-29,38,14,-20,0,-4),
        (7,0.15,-0.05,5,7,-4,-34,42,10,-16,-3,0),
        (8,0.23,-0.03,16,22,-9,-38,44,8,-13,-5,2),
        (9,0.31,-0.02,29,38,-15,-39,44,6,-10,-7,2),
        (10,0.37,-0.01,38,48,-18,-37,41,5,-8,-8,0),
        (12,0.43,-0.03,45,55,-20,-31,34,8,-11,-6,-3),
        (13,0.45,-0.05,38,46,-17,-25,29,10,-14,-3,-6),
        (16,0.40,-0.02,6,9,-4,-12,18,9,-13,8,-14),
    ]
    for row in body: key_body(arm,*row)
    by={r[0]:r for r in body}
    # Wind-up holds the sword visibly to screen-right. Frames 8->10 cross the camera plane quickly: the blade foreshortens then reappears on screen-left without ever arcing overhead.
    sword_keys=[
        (1,0.20,1.27,-20),
        (3,0.32,1.29,-10),
        (4,0.43,1.30,0),
        (6,0.43,1.26,12),
        (7,0.36,1.22,25),
        (8,0.15,1.19,55),
        (9,-0.05,1.16,140),
        (10,-0.20,1.14,175),
        (12,-0.18,1.10,205),
        (13,-0.10,1.12,225),
        (16,0.20,1.23,380),
    ]
    for f,x,z,a in sword_keys:
        r=by[f]; key_sword(sword,f,x+r[1],z+r[2],a)
    for owner in (arm,sword):
        action=owner.animation_data.action; action.name="GaleSlashBody" if owner is arm else "GaleSlashSword"
        for c in action.fcurves:
            for p in c.keyframe_points:
                p.interpolation="LINEAR" if 7<=p.co.x<=10 else "BEZIER"; p.handle_left_type="AUTO_CLAMPED"; p.handle_right_type="AUTO_CLAMPED"


def setup_scene(canvas):
    s=bpy.context.scene; s.render.engine="BLENDER_EEVEE_NEXT"; s.render.film_transparent=True; s.render.resolution_x=int(canvas[0]); s.render.resolution_y=int(canvas[1]); s.render.resolution_percentage=100; s.render.image_settings.file_format="PNG"; s.render.image_settings.color_mode="RGBA"; s.render.image_settings.color_depth="8"; s.view_settings.look="AgX - Medium High Contrast"
    if getattr(s,"eevee",None) is not None: s.eevee.taa_render_samples=8
    bpy.ops.object.light_add(type="AREA",location=(0,-4,5)); light=bpy.context.object; light.data.energy=700; light.data.size=5
    bpy.ops.object.camera_add(location=(0.22,-7.5,2.28)); cam=bpy.context.object; cam.data.type="ORTHO"; cam.data.ortho_scale=3.75; cam.rotation_euler=(Vector((0.22,0,1.08))-cam.location).to_track_quat("-Z","Y").to_euler(); s.camera=cam; s.world.color=(0.035,0.035,0.035)
def sample_debug(arm,sword,frames):
    out=[]
    for f in range(1,frames+1):
        bpy.context.scene.frame_set(f); bpy.context.view_layer.update(); tip=sword.matrix_world@Vector((0,0,1.20)); la=arm.matrix_world@arm.pose.bones["LeftLeg"].tail; ra=arm.matrix_world@arm.pose.bones["RightLeg"].tail
        out.append({"frame":f,"rootX":round(arm.location.x,6),"rootZ":round(arm.location.z,6),"swordTip":[round(tip.x,6),round(tip.y,6),round(tip.z,6)],"leftAnkle":[round(la.x,6),round(la.z,6)],"rightAnkle":[round(ra.x,6),round(ra.z,6)]})
    return out
def main():
    p=argparse.ArgumentParser(add_help=False); p.add_argument("--spec",required=True); p.add_argument("--output",required=True); a,_=p.parse_known_args(argv()); source=json.loads(Path(a.spec).read_text()); output=Path(a.output); frames=int(source["frames"])
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False); arm=build_rig(); build_character(arm); sword=build_sword_and_right_ik(arm); animate(arm,sword,frames); setup_scene(source["canvas"])
    (output/"motion_debug.json").write_text(json.dumps({"action":source["action"],"samples":sample_debug(arm,sword,frames)},indent=2)+"\n"); bpy.context.scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str((output/"source.blend").resolve())); fd=output/"frames"; fd.mkdir(parents=True,exist_ok=True)
    for f in range(1,frames+1): bpy.context.scene.frame_set(f); bpy.context.scene.render.filepath=str((fd/f"{f:02d}.png").resolve()); bpy.ops.render.render(write_still=True)
    print(f"anim2sheet Blender render OK: {frames} frames"); return 0

if __name__=="__main__": raise SystemExit(main())
