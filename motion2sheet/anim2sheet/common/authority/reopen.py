"""Saved-blend joint and proxy authority diagnostic for an execution frame subset."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

JOINT_BONES = {
    "leftShoulder": ("LeftUpperArm", "head"), "leftElbow": ("LeftUpperArm", "tail"),
    "leftWrist": ("LeftForeArm", "tail"), "rightShoulder": ("RightUpperArm", "head"),
    "rightElbow": ("RightUpperArm", "tail"), "rightWrist": ("RightForeArm", "tail"),
}
AUTHORED_JOINTS = {"leftElbow": "leftElbow", "leftWrist": "leftWrist", "rightElbow": "rightElbow", "rightWrist": "rightWrist"}
PROXY_SEGMENTS = {
    "Body_LeftUpperArm": "LeftUpperArm", "Body_LeftForeArm": "LeftForeArm",
    "Body_RightUpperArm": "RightUpperArm", "Body_RightForeArm": "RightForeArm",
    "Review_LeftClavicle": "LeftClavicle", "Review_RightClavicle": "RightClavicle",
    "Review_LeftHand": "LeftHand", "Review_RightHand": "RightHand",
}
OVERLAY_BONES = ["Spine", "Chest", "Neck", "Head", "LeftClavicle", "LeftUpperArm", "LeftForeArm", "LeftHand",
                 "RightClavicle", "RightUpperArm", "RightForeArm", "RightHand", "LeftThigh", "LeftShin", "LeftFoot",
                 "RightThigh", "RightShin", "RightFoot"]


def argv(): return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def vec(values): return [round(float(v), 6) for v in values]
def distance(a, b): return round((Vector(a) - Vector(b)).length, 6)
def find_armature():
    values = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(values) != 1: raise RuntimeError(f"expected exactly one armature after reopen, got {len(values)}")
    return values[0]
def bone_point_world(arm, bone_name, endpoint):
    bone = arm.pose.bones[bone_name]; point = bone.head if endpoint == "head" else bone.tail
    return arm.matrix_world @ point
def sample_joint_positions(arm): return {name: vec(bone_point_world(arm, b, e)) for name, (b, e) in JOINT_BONES.items()}
def average(points):
    total = Vector((0.0, 0.0, 0.0))
    for point in points: total += point
    return total / len(points)

def sample_proxy_segment(obj, arm, bone_name, depsgraph):
    rest = arm.data.bones[bone_name]; head = Vector(rest.head_local); tail = Vector(rest.tail_local); axis = tail - head
    if axis.length < 1e-8: raise RuntimeError(f"{bone_name} has zero rest length")
    axis.normalize(); center = (head + tail) * 0.5; negative = []; positive = []
    for vertex in obj.data.vertices:
        (positive if (Vector(vertex.co) - center).dot(axis) >= 0.0 else negative).append(vertex.index)
    if not negative or not positive: raise RuntimeError(f"{obj.name}: could not identify both cylinder caps")
    evaluated = obj.evaluated_get(depsgraph); mesh = evaluated.to_mesh()
    try:
        start = average([evaluated.matrix_world @ mesh.vertices[i].co for i in negative])
        end = average([evaluated.matrix_world @ mesh.vertices[i].co for i in positive])
    finally: evaluated.to_mesh_clear()
    bone_head = bone_point_world(arm, bone_name, "head"); bone_tail = bone_point_world(arm, bone_name, "tail")
    direct = max((start-bone_head).length, (end-bone_tail).length); flipped_error = max((end-bone_head).length, (start-bone_tail).length)
    flipped = flipped_error < direct
    if flipped: start, end, endpoint_error = end, start, flipped_error
    else: endpoint_error = direct
    mesh_axis = end-start; bone_axis = bone_tail-bone_head
    angle = 180.0 if mesh_axis.length < 1e-8 or bone_axis.length < 1e-8 else math.degrees(math.acos(max(-1.0, min(1.0, float(mesh_axis.normalized().dot(bone_axis.normalized()))))))
    mesh_center=(start+end)*0.5; bone_center=(bone_head+bone_tail)*0.5
    return {"object":obj.name,"bone":bone_name,"missing":False,"flippedToMatch":flipped,"meshStart":vec(start),"meshEnd":vec(end),
            "meshCenter":vec(mesh_center),"boneHead":vec(bone_head),"boneTail":vec(bone_tail),"boneCenter":vec(bone_center),
            "endpointError":round(endpoint_error,6),"centerError":round((mesh_center-bone_center).length,6),"axisAngleDeg":round(angle,6),
            "lengthError":round(abs(mesh_axis.length-bone_axis.length),6)}
def project_pixel(scene,camera,point):
    ndc=world_to_camera_view(scene,camera,point); w=float(scene.render.resolution_x*scene.render.resolution_percentage/100.0); h=float(scene.render.resolution_y*scene.render.resolution_percentage/100.0)
    return [round(ndc.x*w,3),round((1.0-ndc.y)*h,3)]
def projected_bones(scene,arm):
    if scene.camera is None: raise RuntimeError("saved scene has no camera")
    return [{"bone":name,"headWorld":vec(bone_point_world(arm,name,"head")),"tailWorld":vec(bone_point_world(arm,name,"tail")),
             "headPx":project_pixel(scene,scene.camera,bone_point_world(arm,name,"head")),"tailPx":project_pixel(scene,scene.camera,bone_point_world(arm,name,"tail"))}
            for name in OVERLAY_BONES if name in arm.pose.bones]
def main():
    p=argparse.ArgumentParser(add_help=False); p.add_argument("--output",required=True); p.add_argument("--contract",required=True); p.add_argument("--pre-debug",required=True); p.add_argument("--frames",required=True); args,_=p.parse_known_args(argv())
    output=Path(args.output).resolve(); contract=json.loads(Path(args.contract).read_text(encoding="utf-8")); frames=[int(v) for v in args.frames.split(",") if v.strip()]
    contract_frames=[int(v) for v in contract.get("reviewFrames",[])]; invalid=[f for f in frames if f not in contract_frames]
    if not frames or invalid: raise RuntimeError(f"invalid authority execution frames {frames}; outside contract={invalid}")
    pre_debug=json.loads(Path(args.pre_debug).read_text(encoding="utf-8")); pre_by_frame={int(row["frame"]):row for row in pre_debug["samples"]}
    if sorted(pre_by_frame)!=frames: raise RuntimeError(f"pre-save samples do not match execution frames: {sorted(pre_by_frame)} != {frames}")
    arm=find_armature(); scene=bpy.context.scene; depsgraph=bpy.context.evaluated_depsgraph_get(); rows=[]; max_pre=max_auth_pre=max_auth_post=max_ep=max_center=max_angle=max_len=0.0
    for frame in frames:
        scene.frame_set(frame); bpy.context.view_layer.update(); post=sample_joint_positions(arm); pre=pre_by_frame[frame]["joints"]; authored=contract["poses"][str(frame)]; joints={}
        for name in JOINT_BONES:
            row={"preSave":pre[name],"postReopen":post[name],"prePostError":distance(pre[name],post[name])}; max_pre=max(max_pre,row["prePostError"]); key=AUTHORED_JOINTS.get(name)
            if key:
                row["authored"]=authored[key]; row["authoredPreError"]=distance(authored[key],pre[name]); row["authoredPostError"]=distance(authored[key],post[name]); max_auth_pre=max(max_auth_pre,row["authoredPreError"]); max_auth_post=max(max_auth_post,row["authoredPostError"])
            joints[name]=row
        proxies={}
        for object_name,bone_name in PROXY_SEGMENTS.items():
            obj=bpy.data.objects.get(object_name)
            if obj is None: proxies[object_name]={"object":object_name,"bone":bone_name,"missing":True}; continue
            row=sample_proxy_segment(obj,arm,bone_name,depsgraph); proxies[object_name]=row; max_ep=max(max_ep,row["endpointError"]); max_center=max(max_center,row["centerError"]); max_angle=max(max_angle,row["axisAngleDeg"]); max_len=max(max_len,row["lengthError"])
        rows.append({"frame":frame,"joints":joints,"proxySegments":proxies,"bonePixelSegments":projected_bones(scene,arm)})
    result={"mode":"saved-blend-authority-diagnostic","frames":frames,"sourceBlend":bpy.data.filepath,"renderSize":[int(scene.render.resolution_x*scene.render.resolution_percentage/100),int(scene.render.resolution_y*scene.render.resolution_percentage/100)],
            "summary":{"maxPrePostJointError":round(max_pre,6),"maxAuthoredPreSaveJointError":round(max_auth_pre,6),"maxAuthoredPostReopenJointError":round(max_auth_post,6),"maxProxyEndpointError":round(max_ep,6),"maxProxyCenterError":round(max_center,6),"maxProxyAxisAngleDeg":round(max_angle,6),"maxProxyLengthError":round(max_len,6)},"framesData":rows}
    (output/"reopen_debug.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result["summary"],indent=2),flush=True); return 0
if __name__=="__main__": raise SystemExit(main())
