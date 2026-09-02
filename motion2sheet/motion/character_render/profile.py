from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import json5

EPS = 1e-12


def _keys(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise ValueError(f"{label} contains unknown fields: {sorted(extra)}")


def _vec3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise ValueError(f"{label} must be a numeric vec3")
    return float(value[0]), float(value[1]), float(value[2])


def _sub(a, b): return a[0]-b[0], a[1]-b[1], a[2]-b[2]
def _dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _cross(a, b): return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]
def _length(v): return math.sqrt(_dot(v, v))
def _unit(v):
    n = _length(v)
    if n <= EPS: raise ValueError("zero-length bone in rest skeleton")
    return v[0]/n, v[1]/n, v[2]/n

# Blender-compatible edit-bone +Y/roll basis. Kept generic here; PR #11 stays untouched.
def _axis_angle(axis, angle):
    x,y,z=_unit(axis); c=math.cos(angle); s=math.sin(angle); t=1-c
    return ((t*x*x+c,t*x*y-s*z,t*x*z+s*y),(t*x*y+s*z,t*y*y+c,t*y*z-s*x),(t*x*z-s*y,t*y*z+s*x,t*z*z+c))

def _mul3(a,b): return tuple(tuple(sum(a[r][k]*b[k][c] for k in range(3)) for c in range(3)) for r in range(3))
def _transpose3(a): return tuple(tuple(a[c][r] for c in range(3)) for r in range(3))

def _vec_roll_to_mat3(vector, roll):
    x,y,z=_unit(vector); theta=1.0+y; theta_alt=x*x+z*z
    safe=6.1e-3; critical=2.5e-4
    if theta > safe or theta_alt > critical*critical:
        if theta <= safe: theta=theta_alt*0.5+theta_alt*theta_alt*0.125
        base=((1-x*x/theta,x,-x*z/theta),(-x,y,-z),(-x*z/theta,z,1-z*z/theta))
    else:
        base=((-1.0,0.0,0.0),(0.0,-1.0,0.0),(0.0,0.0,1.0))
    return _mul3(_axis_angle((x,y,z), float(roll)), base)

def _rotation_error_deg(a,b):
    d=_mul3(_transpose3(a),b); cosine=max(-1.0,min(1.0,(d[0][0]+d[1][1]+d[2][2]-1.0)*0.5))
    return math.degrees(math.acos(cosine))


def load_character_profile(path: Path) -> dict[str, Any]:
    data=json5.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise ValueError("character profile root must be an object")
    _keys(data,{"schema","version","id","rig","appearance"},"character profile")
    if data.get("schema")!="motion2sheet.character" or data.get("version")!=1: raise ValueError("unsupported character profile schema/version")
    if not isinstance(data.get("id"),str) or not data["id"]: raise ValueError("character profile id is required")
    rig=data.get("rig"); appearance=data.get("appearance")
    if not isinstance(rig,dict) or not isinstance(appearance,dict): raise ValueError("character profile rig/appearance objects are required")
    _keys(rig,{"canonicalRig","restConvention","coordinateSystem","objectTransform","boneEncoding","bones","rootMotion","nonRootTranslation","compatibility"},"character rig")
    if rig.get("restConvention")!="blender-edit-bone-y-axis-roll-v1": raise ValueError("unsupported character restConvention")
    bones=rig.get("bones")
    if not isinstance(bones,list) or not bones: raise ValueError("character rig bones must be non-empty")
    if rig.get("boneEncoding") == "[name,parentIndex,hx,hy,hz,tx,ty,tz,roll]":
        decoded=[]
        for i,row in enumerate(bones):
            if not isinstance(row,list) or len(row)!=9: raise ValueError(f"character compact bone[{i}] must contain 9 fields")
            name=row[0]; parent_index=row[1]
            if not isinstance(parent_index,int) or isinstance(parent_index,bool) or parent_index < -1 or parent_index >= i: raise ValueError(f"invalid compact parent index for bone[{i}]")
            decoded.append({"name":name,"parent":None if parent_index==-1 else decoded[parent_index]["name"],"head":[row[2],row[3],row[4]],"tail":[row[5],row[6],row[7]],"roll":row[8]})
        bones=decoded; rig["bones"]=decoded
    names=set(); parents={}
    for i,row in enumerate(bones):
        if not isinstance(row,dict): raise ValueError(f"character bone[{i}] must be object")
        _keys(row,{"name","parent","head","tail","roll"},f"character bone[{i}]")
        name=row.get("name"); parent=row.get("parent")
        if not isinstance(name,str) or not name or name in names: raise ValueError(f"invalid/duplicate character bone name: {name!r}")
        if parent is not None and not isinstance(parent,str): raise ValueError(f"invalid parent for {name}")
        _vec3(row.get("head"),f"{name}.head"); _vec3(row.get("tail"),f"{name}.tail")
        if isinstance(row.get("roll"),bool) or not isinstance(row.get("roll"),(int,float)): raise ValueError(f"{name}.roll must be numeric")
        if _length(_sub(tuple(row["tail"]),tuple(row["head"])))<=EPS: raise ValueError(f"zero-length character bone: {name}")
        names.add(name); parents[name]=parent
    for name,parent in parents.items():
        if parent is not None and parent not in names: raise ValueError(f"character bone parent missing: {name}->{parent}")
    root=rig.get("rootMotion",{}); nonroot=rig.get("nonRootTranslation",{})
    if root.get("policy")!="scale-by-stature" or not isinstance(root.get("bone"),str): raise ValueError("rootMotion must declare bone + scale-by-stature")
    if nonroot.get("policy")!="scale-by-bone-length": raise ValueError("nonRootTranslation policy must be scale-by-bone-length")
    return data


def load_camera_profile(path: Path) -> dict[str, Any]:
    data=json5.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise ValueError("camera profile root must be object")
    _keys(data,{"schema","version","id","projection","location","target","upAxis","orthoScale","followRoot","margin"},"camera profile")
    if data.get("schema")!="motion2sheet.camera" or data.get("version")!=1: raise ValueError("unsupported camera profile schema/version")
    if data.get("projection")!="ORTHO": raise ValueError("POC supports ORTHO camera only")
    _vec3(data.get("location"),"camera.location"); _vec3(data.get("target"),"camera.target"); _vec3(data.get("upAxis"),"camera.upAxis")
    if not isinstance(data.get("followRoot"),bool): raise ValueError("camera.followRoot must be boolean")
    if isinstance(data.get("orthoScale"),bool) or not isinstance(data.get("orthoScale"),(int,float)) or data["orthoScale"]<=0: raise ValueError("camera.orthoScale must be positive")
    return data


def _bone_rows_from_source(source_rig: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows={}
    for bone in source_rig.get("bones",[]):
        geo=bone.get("editGeometry",{})
        rows[bone["name"]]={"name":bone["name"],"parent":bone.get("parent"),"head":geo.get("head"),"tail":geo.get("tail"),"roll":geo.get("roll")}
    return rows

def _basis_rows(rows: dict[str, dict[str, Any]]):
    absolute={name:_vec_roll_to_mat3(_sub(tuple(row["tail"]),tuple(row["head"])),float(row["roll"])) for name,row in rows.items()}
    local={}
    for name,row in rows.items():
        parent=row["parent"]
        local[name]=absolute[name] if parent is None else _mul3(_transpose3(absolute[parent]),absolute[name])
    return local

def _bone_length(row): return _length(_sub(tuple(row["tail"]),tuple(row["head"])))
def _stature(rows):
    if "mixamorig:Hips" not in rows or "mixamorig:HeadTop_End" not in rows: raise ValueError("Mixamo-compatible rig requires Hips and HeadTop_End for stature policy")
    return _length(_sub(tuple(rows["mixamorig:HeadTop_End"]["tail"]),tuple(rows["mixamorig:Hips"]["head"])))


def validate_character_compatibility(source_rig: dict[str, Any], character: dict[str, Any]) -> dict[str, Any]:
    source=_bone_rows_from_source(source_rig); target={row["name"]:row for row in character["rig"]["bones"]}
    source_names=set(source); target_names=set(target)
    missing=sorted(source_names-target_names); extra=sorted(target_names-source_names)
    if missing or extra: raise ValueError(f"character rig bone set incompatible: missing={missing} extra={extra}")
    topology=[]
    for name in sorted(source_names):
        if source[name]["parent"]!=target[name]["parent"]: topology.append({"bone":name,"sourceParent":source[name]["parent"],"characterParent":target[name]["parent"]})
    if topology: raise ValueError(f"character rig parent topology incompatible: {topology[:4]}")
    src_coord=source_rig.get("coordinateSystem",{}); dst_coord=character["rig"].get("coordinateSystem",{})
    for key in ("handedness","rightAxis","forwardAxis","upAxis"):
        if src_coord.get(key)!=dst_coord.get(key): raise ValueError(f"character coordinate convention mismatch for {key}: source={src_coord.get(key)!r} character={dst_coord.get(key)!r}")
    src_basis=_basis_rows(source); dst_basis=_basis_rows(target)
    tolerance=float(character["rig"].get("compatibility",{}).get("restOrientationToleranceDegrees",0.001))
    max_error=-1.0; worst=None
    for name in sorted(source_names):
        error=_rotation_error_deg(src_basis[name],dst_basis[name])
        if error>max_error: max_error=error; worst=name
        if error>tolerance: raise ValueError(f"character rest orientation incompatible: {name} error={error:.9f}deg tolerance={tolerance}deg")
    source_stature=_stature(source); char_stature=_stature(target); root_scale=char_stature/source_stature
    ratios={name:_bone_length(target[name])/_bone_length(source[name]) for name in source_names}
    root=character["rig"]["rootMotion"]["bone"]
    if root not in source_names: raise ValueError(f"root motion bone missing: {root}")
    ratios[root]=root_scale
    return {"pass":True,"canonicalRig":character["rig"]["canonicalRig"],"boneCount":len(source_names),"maxRestOrientationErrorDegrees":max_error,"worstRestOrientationBone":worst,"rootBone":root,"rootTranslationPolicy":"scale-by-stature","rootTranslationScale":root_scale,"nonRootTranslationPolicy":"scale-by-bone-length","translationScales":ratios}
