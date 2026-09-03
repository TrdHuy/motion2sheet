"""Real model + rig + skin Contract B rendering.

Keep package import Blender-safe: Blender scripts import submodules from this
package using Blender's bundled Python, which does not include Pillow. Public
CLI code imports the runner explicitly from motion2sheet.motion.model_render.runner.
"""

__all__: list[str] = []
