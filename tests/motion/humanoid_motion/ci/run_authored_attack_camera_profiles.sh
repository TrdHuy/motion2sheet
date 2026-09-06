#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

ROOT="${1:-build/motion/direct-authored-attack-camera-profiles}"
FIXTURES="tests/motion/humanoid_motion/fixtures/release_assets.json"
MAPPING="profiles/humanoid_motion/mixamo_humanoid_v1.json"
COMMITTED="samples/humanoid_motion/animations/heavy-right-cross/animation.json"
CAMERA_KEYS=("front" "side" "topdown-game")
CAMERA_PATHS=(
  "profiles/cameras/front_humanoid_motion.json5"
  "profiles/cameras/side_humanoid_motion.json5"
  "profiles/cameras/topdown_game_humanoid_motion.json5"
)
TMP_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TMP_ROOT="$TMP_PARENT/motion2sheet-attack-camera-profiles-$$"
mkdir -p "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

rm -rf "$ROOT"
mkdir -p "$ROOT/diagnostics/cameras"
cp "$COMMITTED" "$ROOT/animation.json"
cp "$FIXTURES" "$ROOT/diagnostics/release_assets.json"
for camera_path in "${CAMERA_PATHS[@]}"; do
  test -s "$camera_path"
  cp "$camera_path" "$ROOT/diagnostics/cameras/$(basename "$camera_path")"
done

mapfile -t CHARACTER_KEYS < <(python - "$FIXTURES" <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key, asset in sorted(manifest["assets"].items()):
    if "without-skin" not in str(asset["filename"]).lower():
        print(key)
PY
)
test "${#CHARACTER_KEYS[@]}" -eq 3

for camera_key in "${CAMERA_KEYS[@]}"; do
  mkdir -p "$ROOT/$camera_key/diagnostics" "$ROOT/$camera_key/characters"
  cp "$COMMITTED" "$ROOT/$camera_key/animation.json"
done

for key in "${CHARACTER_KEYS[@]}"; do
  safe_key="${key//_/-}"
  mapfile -t ASSET < <(python - "$FIXTURES" "$key" <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
asset = manifest["assets"][sys.argv[2]]
print(manifest["releaseUrl"])
print(asset["filename"])
print(asset["url"])
print(asset["sha256"])
print(asset["size"])
PY
  )
  RELEASE_URL="${ASSET[0]}"
  FILENAME="${ASSET[1]}"
  URL="${ASSET[2]}"
  EXPECTED_SHA="${ASSET[3]}"
  EXPECTED_SIZE="${ASSET[4]}"
  case "$URL" in
    "https://github.com/TrdHuy/motion2sheet/releases/download/e2e_gh_action_asset/"*) ;;
    *) echo "unexpected fixture URL: $URL" >&2; exit 1 ;;
  esac

  FBX="$TMP_ROOT/${safe_key}__${FILENAME}"
  curl -fL --retry 3 --retry-delay 2 -o "$FBX" "$URL"
  ACTUAL_SHA="$(sha256sum "$FBX" | awk '{print $1}')"
  ACTUAL_SIZE="$(stat -c %s "$FBX")"
  test "$ACTUAL_SHA" = "$EXPECTED_SHA"
  test "$ACTUAL_SIZE" -eq "$EXPECTED_SIZE"

  CHARACTER_DIR="$TMP_ROOT/character-$safe_key"
  motion2sheet export-character "$FBX" --output "$CHARACTER_DIR"
  test -s "$CHARACTER_DIR/model.glb"
  test -s "$CHARACTER_DIR/rig.json"
  test -s "$CHARACTER_DIR/skin.json"

  COMMON="$TMP_ROOT/common-$safe_key"
  mkdir -p "$COMMON/character-export"
  cp -R "$CHARACTER_DIR/diagnostics/." "$COMMON/character-export/"
  export key safe_key RELEASE_URL FILENAME URL EXPECTED_SHA EXPECTED_SIZE ACTUAL_SHA ACTUAL_SIZE
  python - "$COMMON/release-asset-verification.json" <<'PY'
import json, os, sys
from pathlib import Path
report = {
    "schema": "motion2sheet.humanoid-motion.release-asset-verification",
    "version": 1,
    "assetKey": os.environ["key"], "outputKey": os.environ["safe_key"],
    "releaseUrl": os.environ["RELEASE_URL"], "filename": os.environ["FILENAME"],
    "url": os.environ["URL"], "expectedSha256": os.environ["EXPECTED_SHA"],
    "actualSha256": os.environ["ACTUAL_SHA"], "expectedSize": int(os.environ["EXPECTED_SIZE"]),
    "actualSize": int(os.environ["ACTUAL_SIZE"]), "sha256Pass": True, "sizePass": True,
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  python - "$CHARACTER_DIR" "$MAPPING" "$COMMON/character-mapping.json" <<'PY'
import json, sys
from pathlib import Path
from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, read_mapping, validate_character_mapping
from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import validate_skin_document
character = Path(sys.argv[1])
rig = validate_rig_document(read_json(character / "rig.json"))
mapping = validate_character_mapping(read_mapping(Path(sys.argv[2])), rig)
validate_skin_document(read_json(character / "skin.json"), rig)
report = mapping_diagnostics(mapping, rig)
assert report["leftRightVerification"]["pass"] is True
report["skinValidationPass"] = True
report["rigId"] = rig["id"]
Path(sys.argv[3]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  for i in "${!CAMERA_KEYS[@]}"; do
    camera_key="${CAMERA_KEYS[$i]}"
    camera_path="${CAMERA_PATHS[$i]}"
    CAM_ROOT="$ROOT/$camera_key"
    CHAR_ROOT="$CAM_ROOT/characters/$safe_key"
    mkdir -p "$CHAR_ROOT/diagnostics/character-export"
    cp "$COMMON/release-asset-verification.json" "$CHAR_ROOT/diagnostics/release-asset-verification.json"
    cp "$COMMON/character-mapping.json" "$CHAR_ROOT/diagnostics/character-mapping.json"
    cp -R "$COMMON/character-export/." "$CHAR_ROOT/diagnostics/character-export/"

    RENDER_TMP="$TMP_ROOT/render-$safe_key-$camera_key"
    motion2sheet render-humanoid-animation \
      --model "$CHARACTER_DIR/model.glb" \
      --character-rig "$CHARACTER_DIR/rig.json" \
      --skin "$CHARACTER_DIR/skin.json" \
      --character-mapping "$MAPPING" \
      --animation "$CAM_ROOT/animation.json" \
      --camera-profile "$camera_path" \
      --sample-count 10 --output-fps 8 --canvas 224x224 \
      --sheet-columns 5 --render-samples 1 --gif \
      --output "$RENDER_TMP"

    mv "$RENDER_TMP/pose_sheet.png" "$CHAR_ROOT/${safe_key}__pose_sheet.png"
    mv "$RENDER_TMP/preview.gif" "$CHAR_ROOT/${safe_key}__preview.gif"
    mv "$RENDER_TMP/render.json" "$CHAR_ROOT/${safe_key}__render.json"
    mkdir -p "$CHAR_ROOT/diagnostics/render"
    cp -R "$RENDER_TMP/diagnostics/." "$CHAR_ROOT/diagnostics/render/"
    rm -f "$RENDER_TMP/runtime.blend"
  done
done

for i in "${!CAMERA_KEYS[@]}"; do
  camera_key="${CAMERA_KEYS[$i]}"
  python tests/motion/humanoid_motion/ci/verify_authored_attack_multi_character.py \
    --root "$ROOT/$camera_key" --fixtures "$FIXTURES" --mapping "$MAPPING" \
    --output "$ROOT/$camera_key/summary.json"
  test -s "$ROOT/$camera_key/summary.json"
  for key in "${CHARACTER_KEYS[@]}"; do
    safe_key="${key//_/-}"
    test -s "$ROOT/$camera_key/characters/$safe_key/${safe_key}__pose_sheet.png"
    test -s "$ROOT/$camera_key/characters/$safe_key/${safe_key}__preview.gif"
  done
done

python - "$ROOT" "${CAMERA_KEYS[*]}" "${CAMERA_PATHS[*]}" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
keys = sys.argv[2].split()
paths = sys.argv[3].split()
cameras = {}
for key, path in zip(keys, paths):
    summary = json.loads((root / key / "summary.json").read_text(encoding="utf-8"))
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    assert summary["pass"] is True
    cameras[key] = {"profile": profile, "summary": summary}
report = {
    "schema": "motion2sheet.humanoid-motion.authored-attack-camera-profile-summary",
    "version": 1,
    "pass": True,
    "animationId": "heavy-right-cross",
    "cameraCount": len(cameras),
    "characterCount": 3,
    "renderCellCount": len(cameras) * 3,
    "gifCount": len(cameras) * 3,
    "poseSheetCount": len(cameras) * 3,
    "cameras": cameras,
}
(root / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

test -s "$ROOT/summary.json"
echo "Heavy Right Cross camera-profile review PASS: $ROOT"
