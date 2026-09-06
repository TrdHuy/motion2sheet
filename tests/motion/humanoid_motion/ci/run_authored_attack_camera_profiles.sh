#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

ROOT="${1:-build/motion/direct-authored-attack-camera-profiles}"
FIXTURES="tests/motion/humanoid_motion/fixtures/release_assets.json"
MAPPING="profiles/humanoid_motion/mixamo_humanoid_v1.json"
COMMITTED="samples/humanoid_motion/animations/heavy-right-cross/animation.json"
CHARACTER_KEY="character-a"
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

mapfile -t ASSET < <(python - "$FIXTURES" "$CHARACTER_KEY" <<'PY'
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

FBX="$TMP_ROOT/$FILENAME"
curl -fL --retry 3 --retry-delay 2 -o "$FBX" "$URL"
ACTUAL_SHA="$(sha256sum "$FBX" | awk '{print $1}')"
ACTUAL_SIZE="$(stat -c %s "$FBX")"
test "$ACTUAL_SHA" = "$EXPECTED_SHA"
test "$ACTUAL_SIZE" -eq "$EXPECTED_SIZE"

CHARACTER_DIR="$TMP_ROOT/character-a"
motion2sheet export-character "$FBX" --output "$CHARACTER_DIR"
test -s "$CHARACTER_DIR/model.glb"
test -s "$CHARACTER_DIR/rig.json"
test -s "$CHARACTER_DIR/skin.json"

python - "$CHARACTER_DIR" "$MAPPING" <<'PY'
from pathlib import Path
import sys
from motion2sheet.motion.humanoid_motion.mapping import read_mapping, validate_character_mapping
from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import validate_skin_document
character = Path(sys.argv[1])
rig = validate_rig_document(read_json(character / "rig.json"))
validate_character_mapping(read_mapping(Path(sys.argv[2])), rig)
validate_skin_document(read_json(character / "skin.json"), rig)
PY

ANIMATION_SHA="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
for i in "${!CAMERA_KEYS[@]}"; do
  camera_key="${CAMERA_KEYS[$i]}"
  camera_path="${CAMERA_PATHS[$i]}"
  CAM_ROOT="$ROOT/$camera_key"
  OUT="$CAM_ROOT/character-a"
  mkdir -p "$OUT"

  BEFORE="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
  motion2sheet render-humanoid-animation \
    --model "$CHARACTER_DIR/model.glb" \
    --character-rig "$CHARACTER_DIR/rig.json" \
    --skin "$CHARACTER_DIR/skin.json" \
    --character-mapping "$MAPPING" \
    --animation "$ROOT/animation.json" \
    --camera-profile "$camera_path" \
    --sample-count 10 --output-fps 8 --canvas 224x224 \
    --sheet-columns 5 --render-samples 1 --gif \
    --output "$TMP_ROOT/render-$camera_key"
  AFTER="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
  test "$BEFORE" = "$AFTER"

  mv "$TMP_ROOT/render-$camera_key/pose_sheet.png" "$OUT/character-a__${camera_key}__pose_sheet.png"
  mv "$TMP_ROOT/render-$camera_key/preview.gif" "$OUT/character-a__${camera_key}__preview.gif"
  mv "$TMP_ROOT/render-$camera_key/render.json" "$OUT/character-a__${camera_key}__render.json"
  mkdir -p "$OUT/diagnostics"
  cp -R "$TMP_ROOT/render-$camera_key/diagnostics/." "$OUT/diagnostics/"
  rm -f "$TMP_ROOT/render-$camera_key/runtime.blend"

  python - "$OUT/character-a__${camera_key}__render.json" "$ANIMATION_SHA" "$camera_key" <<'PY'
import json, sys
from pathlib import Path
render = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_sha = sys.argv[2]
assert render["renderedSamples"] == list(range(10))
assert render["frameCount"] == 10
assert float(render["fps"]) == 8.0 and float(render["outputFps"]) == 8.0
assert render["animationSha256Before"] == render["animationSha256After"] == expected_sha
assert render["animationMutated"] is False
assert render["playback"]["pass"] is True and render["playback"]["nanInfCheck"] is True
assert render["rootMotion"]["canonical"]["isInPlace"] is True
assert render["semanticMapping"]["leftRightVerification"]["pass"] is True
PY

done

export RELEASE_URL FILENAME URL EXPECTED_SHA EXPECTED_SIZE ACTUAL_SHA ACTUAL_SIZE ANIMATION_SHA
python - "$ROOT" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
keys = ["front", "side", "topdown-game"]
profiles = {
    "front": root / "diagnostics/cameras/front_humanoid_motion.json5",
    "side": root / "diagnostics/cameras/side_humanoid_motion.json5",
    "topdown-game": root / "diagnostics/cameras/topdown_game_humanoid_motion.json5",
}
cameras = {}
for key in keys:
    out = root / key / "character-a"
    pose = out / f"character-a__{key}__pose_sheet.png"
    gif = out / f"character-a__{key}__preview.gif"
    render_path = out / f"character-a__{key}__render.json"
    assert pose.is_file() and gif.is_file() and render_path.is_file()
    cameras[key] = {
        "profile": json.loads(profiles[key].read_text(encoding="utf-8")),
        "poseSheet": str(pose.relative_to(root)),
        "previewGif": str(gif.relative_to(root)),
        "renderJson": str(render_path.relative_to(root)),
    }
report = {
    "schema": "motion2sheet.humanoid-motion.authored-attack-character-a-camera-summary",
    "version": 1,
    "pass": True,
    "animationId": "heavy-right-cross",
    "animationSha256": os.environ["ANIMATION_SHA"],
    "characterKey": "character-a",
    "asset": {
        "filename": os.environ["FILENAME"],
        "url": os.environ["URL"],
        "expectedSha256": os.environ["EXPECTED_SHA"],
        "actualSha256": os.environ["ACTUAL_SHA"],
        "expectedSize": int(os.environ["EXPECTED_SIZE"]),
        "actualSize": int(os.environ["ACTUAL_SIZE"]),
    },
    "cameraCount": 3,
    "renderCellCount": 3,
    "gifCount": 3,
    "poseSheetCount": 3,
    "cameras": cameras,
}
(root / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

test -s "$ROOT/summary.json"
echo "Heavy Right Cross Character A camera review PASS: $ROOT"
