from __future__ import annotations

import hashlib
import json
from typing import Any


def character_rest_payload(rig: dict[str, Any]) -> dict[str, Any]:
    """Return only canonical character-rest authority, excluding source/clip provenance.

    Character identity must remain stable when the same mesh/rig is downloaded with a
    different Mixamo action. Animation/source metadata is therefore deliberately absent.
    """

    return {
        "coordinateSystem": rig["coordinateSystem"],
        "units": rig["units"],
        "restAuthority": rig["restAuthority"],
        "editGeometrySpace": rig["editGeometrySpace"],
        "armatureTransform": rig["armatureObject"]["transform"],
        "bones": [
            {
                "name": bone["name"],
                "parent": bone["parent"],
                "editGeometry": bone["editGeometry"],
                "properties": bone["properties"],
            }
            for bone in rig["bones"]
        ],
    }


def character_rest_fingerprint(rig: dict[str, Any]) -> str:
    payload = character_rest_payload(rig)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(b"motion2sheet.character-rest.v1\0" + encoded).hexdigest()


def character_rig_id(rig: dict[str, Any]) -> str:
    return f"character-{character_rest_fingerprint(rig)[:16]}-rig-v1"


def character_skin_id(rig: dict[str, Any]) -> str:
    return f"character-{character_rest_fingerprint(rig)[:16]}-skin-v1"
