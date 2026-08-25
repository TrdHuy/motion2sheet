from __future__ import annotations

import argparse
import base64
import io
import textwrap
import zipfile
from pathlib import Path


VERSIONS = ["native_generate_vfx.py"] + [f"native_generate_vfx_v{i}.py" for i in range(2, 49)] + ["vfx_trajectory.py"]


def deterministic_zip(blender_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in VERSIONS:
            path = blender_dir / name
            source = path.read_text(encoding="utf-8")
            if name == "native_generate_vfx_v48.py":
                # V48's final 3D trajectory remains a normal editable source file
                # after consolidation. The frozen compatibility chain receives its
                # location from the wrapper instead of expecting vfx_trajectory_v48.py.
                source = source.replace(
                    "import importlib.util\nfrom pathlib import Path\n",
                    "import importlib.util\nimport os\nfrom pathlib import Path\n",
                    1,
                )
                source = source.replace(
                    '_TRAJECTORY_PATH = Path(__file__).with_name("vfx_trajectory_v48.py")',
                    '_TRAJECTORY_PATH = Path(os.environ["MOTION2SHEET_VFX_TRAJECTORY_PATH"])',
                    1,
                )
                if "MOTION2SHEET_VFX_TRAJECTORY_PATH" not in source:
                    raise RuntimeError("Unable to rewrite V48 trajectory path")
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.encode("utf-8"))
    return buffer.getvalue()


def make_wrapper(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    chunks = "\n".join(f'    "{encoded[i:i+100]}"' for i in range(0, len(encoded), 100))
    return f'''"""Final Blender-native deterministic VFX renderer.

This file freezes the accepted V48 visual implementation into one compatibility
payload so the repository does not retain dozens of development-version files.
Trajectory math remains editable in ``vfx_trajectory.py``. No image processing
happens outside Blender; the payload only reconstructs Python renderer sources in
a temporary directory before executing the accepted renderer.
"""
from __future__ import annotations

import atexit
import base64
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import io

_BUNDLE_B64 = (\n{chunks}\n)
_RUNTIME_DIR: Path | None = None


def _runtime_dir() -> Path:
    global _RUNTIME_DIR
    if _RUNTIME_DIR is not None:
        return _RUNTIME_DIR
    root = Path(tempfile.mkdtemp(prefix="motion2sheet-vfx-"))
    payload = base64.b64decode(_BUNDLE_B64)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        archive.extractall(root)
    _RUNTIME_DIR = root
    atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
    return root


def _load_renderer():
    root = _runtime_dir()
    trajectory_path = Path(__file__).with_name("vfx_trajectory.py").resolve()
    if not trajectory_path.exists():
        raise RuntimeError(f"Missing final Blender trajectory module: {{trajectory_path}}")
    os.environ["MOTION2SHEET_VFX_TRAJECTORY_PATH"] = str(trajectory_path)
    path = root / "native_generate_vfx_v48.py"
    spec = importlib.util.spec_from_file_location("motion2sheet_native_vfx_final", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load frozen final VFX renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_renderer = _load_renderer()
base = _renderer.base


if __name__ == "__main__":
    base.main()
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender-dir", type=Path, default=Path("motion2sheet/blender"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = deterministic_zip(args.blender_dir)
    wrapper = make_wrapper(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(wrapper, encoding="utf-8")
    print(f"Wrote {args.output} ({len(wrapper)} chars; payload {len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
