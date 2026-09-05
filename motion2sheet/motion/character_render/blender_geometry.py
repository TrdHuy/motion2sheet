from __future__ import annotations
import math
import bpy
from mathutils import Matrix, Quaternion, Vector


def matrix_from_transform(t):
    q=Quaternion(tuple(float(v) for v in t['rotationQuaternion']))
    return Matrix.LocRotScale(Vector(tuple(float(v) for v in t['translation'])),q,Vector(tuple(float(v) for v in t['scale'])))


def build_armature(name,bones,transform,hide_render):
    data=bpy.data.armatures.new(name+'Data'); obj=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(obj); obj.matrix_world=matrix_from_transform(transform)
    bpy.context.view_layer.objects.active=obj; obj.select_set(True); bpy.ops.object.mode_set(mode='EDIT'); created={}
    for row in bones:
        eb=data.edit_bones.new(row['name']); eb.head=Vector(tuple(float(x) for x in row['head'])); eb.tail=Vector(tuple(float(x) for x in row['tail'])); eb.roll=float(row['roll']); created[row['name']]=eb
    for row in bones:
        if row['parent'] is not None: created[row['name']].parent=created[row['parent']]
    bpy.ops.object.mode_set(mode='OBJECT'); obj.hide_render=hide_render; return obj


def source_bones(rig):
    return [{'name':b['name'],'parent':b.get('parent'),'head':b['editGeometry']['head'],'tail':b['editGeometry']['tail'],'roll':b['editGeometry']['roll']} for b in rig['bones']]


def material(name,spec):
    mat=bpy.data.materials.new(name); mat.diffuse_color=tuple(float(x) for x in spec.get('baseColor',[0.5,0.5,0.5,1.0])); mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF') if mat.node_tree else None
    if bsdf:
        bsdf.inputs['Base Color'].default_value=mat.diffuse_color; bsdf.inputs['Roughness'].default_value=float(spec.get('roughness',0.6)); bsdf.inputs['Metallic'].default_value=float(spec.get('metallic',0.0))
    return mat


def perp_basis(direction):
    d=direction.normalized(); helper=Vector((0,0,1)) if abs(d.z)<0.9 else Vector((1,0,0)); u=d.cross(helper).normalized(); return u,d.cross(u).normalized()


def tube_geometry(head,tail,radius,segments,verts,faces):
    start=len(verts); u,v=perp_basis(tail-head)
    for p in (head,tail):
        for i in range(segments):
            a=2*math.pi*i/segments; verts.append(tuple(p+u*(math.cos(a)*radius)+v*(math.sin(a)*radius)))
    for i in range(segments):
        j=(i+1)%segments; faces.append((start+i,start+j,start+segments+j,start+segments+i))
    faces.append(tuple(start+i for i in reversed(range(segments)))); faces.append(tuple(start+segments+i for i in range(segments)))
    return list(range(start,start+2*segments))


def build_body(character,arm):
    cfg=character['appearance']['body']; segments=int(cfg.get('radialSegments',8)); ratio=float(cfg.get('radiusLengthRatio',0.12)); minr=float(cfg.get('minRadius',0.2)); maxr=float(cfg.get('maxRadius',3.2)); verts=[]; faces=[]; weights={}
    for row in character['rig']['bones']:
        h=Vector(tuple(row['head'])); t=Vector(tuple(row['tail'])); radius=max(minr,min(maxr,(t-h).length*ratio)); weights[row['name']]=tube_geometry(h,t,radius,segments,verts,faces)
    mesh=bpy.data.meshes.new('CharacterBodyMesh'); mesh.from_pydata(verts,[],faces); mesh.update(); obj=bpy.data.objects.new('CharacterBody',mesh); bpy.context.collection.objects.link(obj); obj.parent=arm; obj.matrix_parent_inverse=Matrix.Identity(4); obj.location=(0,0,0)
    obj.data.materials.append(material('CharacterBodyMaterial',cfg.get('material',{})))
    for bone,indices in weights.items(): obj.vertex_groups.new(name=bone).add(indices,1.0,'REPLACE')
    obj.modifiers.new('CharacterArmature','ARMATURE').object=arm


def box(center,direction,length,width):
    d=direction.normalized(); u,v=perp_basis(d); c=center+d*(length*.5); half=width*.5; a=d*(length*.5); b=u*half; e=v*half
    points=[c+sx*a+sy*b+sz*e for sx in (-1,1) for sy in (-1,1) for sz in (-1,1)]
    return [tuple(p) for p in points],[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]


def build_equipment(character,arm):
    bones={b['name']:b for b in character['rig']['bones']}
    for item in character['appearance'].get('equipment',[]):
        bone=bones[item['attachBone']]; h=Vector(tuple(bone['head'])); t=Vector(tuple(bone['tail'])); verts,faces=box(t,t-h,float(item.get('length',30)),float(item.get('width',1.5)))
        mesh=bpy.data.meshes.new(item['id']+'Mesh'); mesh.from_pydata(verts,[],faces); obj=bpy.data.objects.new(item['id'],mesh); bpy.context.collection.objects.link(obj); obj.parent=arm; obj.matrix_parent_inverse=Matrix.Identity(4); obj.data.materials.append(material(item['id']+'Material',item.get('material',{})))
        obj.vertex_groups.new(name=item['attachBone']).add(list(range(len(verts))),1.0,'REPLACE'); obj.modifiers.new('CharacterArmature','ARMATURE').object=arm
