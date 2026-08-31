from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from io_scene_fbx import parse_fbx


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _find_first(elem, elem_id: bytes):
    for child in elem.elems:
        if child.id == elem_id:
            return child
    return None


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if hasattr(value, "tolist"):
        return value.tolist()
    try:
        return list(value) if type(value).__module__ == "array" else value
    except Exception:
        return value


def _model_name(model) -> str:
    raw = model.props[-2]
    if isinstance(raw, bytes):
        raw = raw.split(b"\x00\x01", 1)[0].decode("utf-8", "replace")
    if raw.startswith("Model::"):
        raw = raw[len("Model::"):]
    return raw


def _properties70(model) -> dict:
    props70 = _find_first(model, b"Properties70")
    if props70 is None:
        return {}
    result = {}
    for prop in props70.elems:
        if prop.id != b"P" or len(prop.props) < 5:
            continue
        name = _decode(prop.props[0])
        values = [_decode(value) for value in prop.props[4:]]
        result[name] = values[0] if len(values) == 1 else values
    return result


def capture(path: Path) -> dict:
    root, version = parse_fbx.parse(str(path), use_namedtuple=True)
    objects = _find_first(root, b"Objects")
    models = []
    if objects is not None:
        for model in objects.elems:
            if model.id != b"Model":
                continue
            model_type = _decode(model.props[-1]) if model.props else None
            props = _properties70(model)
            transform_keys = (
                "Lcl Translation", "Lcl Rotation", "Lcl Scaling",
                "PreRotation", "PostRotation", "RotationOffset", "RotationPivot",
                "ScalingOffset", "ScalingPivot", "RotationOrder", "InheritType",
            )
            models.append({
                "name": _model_name(model),
                "type": model_type,
                "transform": {key: props[key] for key in transform_keys if key in props},
            })
    return {
        "filename": path.name,
        "version": version,
        "models": sorted(models, key=lambda item: item["name"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--reconstructed", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())
    document = {
        "schema": "motion2sheet.fbx-transform-stack-probe",
        "version": 1,
        "source": capture(Path(args.source).resolve()),
        "reconstructed": capture(Path(args.reconstructed).resolve()),
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "sourceModels": len(document["source"]["models"]),
        "reconstructedModels": len(document["reconstructed"]["models"]),
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
