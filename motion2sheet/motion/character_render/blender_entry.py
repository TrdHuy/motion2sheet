from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from motion2sheet.motion.character_render.blender_geometry import build_armature,build_body,build_equipment,source_bones
from motion2sheet.motion.character_render.blender_playback import apply_animation,diagnostics,setup_scene


def args():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []; p=argparse.ArgumentParser(); p.add_argument('--request',required=True); return p.parse_args(argv)

def main():
    a=args(); request=json.loads(Path(a.request).read_text(encoding='utf-8')); rig=json.loads(Path(request['rigPath']).read_text()); animation=json.loads(Path(request['animationPath']).read_text()); request['animationFrames']=animation['frames']
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    source=build_armature('MotionJsonReference',source_bones(rig),rig['armatureObject']['transform'],True); char=build_armature('CharacterRig',request['character']['rig']['bones'],request['character']['rig']['objectTransform'],False); build_body(request['character'],char); build_equipment(request['character'],char)
    source_names=apply_animation(source,animation,{b['name']:1 for b in rig['bones']}); char_names=apply_animation(char,animation,request['compatibility']['translationScales']); setup_scene(request,char)
    scene=bpy.context.scene; scene.render.fps=max(1,round(float(animation['fps']))); scene.render.fps_base=scene.render.fps/float(animation['fps']); scene.frame_start=int(animation['frameRange'][0]); scene.frame_end=int(animation['frameRange'][1]); output=Path(request['output']); frame_dir=output/'.frames'; frame_dir.mkdir(parents=True,exist_ok=True)
    for frame in request['selectedFrames']:
        scene.frame_set(int(frame)); scene.render.filepath=str(frame_dir/f'frame_{int(frame):04d}.png'); bpy.ops.render.render(write_still=True)
    report=diagnostics(source,char,animation,request['compatibility'],source_names,char_names); path=output/'diagnostics'/'playback.json'; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    if not report['pass']: raise RuntimeError(f'direct Motion JSON playback fidelity failed: {report}')
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'source.blend')); print(json.dumps(report,sort_keys=True),flush=True); return 0
if __name__=='__main__': raise SystemExit(main())
