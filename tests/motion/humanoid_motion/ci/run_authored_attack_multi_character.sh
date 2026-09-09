#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

ROOT="${1:-build/motion/direct-authored-attack-multi-character}"
FIXTURES="tests/motion/humanoid_motion/fixtures/release_assets.json"
MAPPING="profiles/humanoid_motion/mixamo_humanoid_v1.json"
GENERATOR="samples/humanoid_motion/animations/heavy-right-cross/generate.py"
COMMITTED="samples/humanoid_motion/animations/heavy-right-cross/animation.json"
TMP_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TMP_ROOT="$TMP_PARENT/motion2sheet-authored-attack-multi-$$"
mkdir -p "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

rm -rf "$ROOT"
mkdir -p "$ROOT/diagnostics" "$ROOT/characters"
cp "$FIXTURES" "$ROOT/diagnostics/release_assets.json"

REVIEW_CAMERA="$ROOT/diagnostics/review-camera.json5"
cat > "$REVIEW_CAMERA" <<'JSON'
{
  "schema": "motion2sheet.camera",
  "version": 1,
  "id": "three_quarter_right_heavy_cross_multi_character",
  "projection": "ORTHO",
  "location": [-3.8, -5.5, 1.30],
  "target": [0.0, -0.12, 1.08],
  "upAxis": [0.0, 0.0, 1.0],
  "orthoScale": 3.15,
  "followRoot": false,
  "margin": 1.0
}
JSON

GEN_A="$TMP_ROOT/generation-a.json"
GEN_B="$TMP_ROOT/generation-b.json"
python "$GENERATOR" --output "$GEN_A"
python "$GENERATOR" --output "$GEN_B"
cmp "$GEN_A" "$GEN_B"
cmp "$GEN_A" "$COMMITTED"
cp "$COMMITTED" "$ROOT/animation.json"
sha256sum "$GEN_A" "$GEN_B" "$COMMITTED" "$ROOT/animation.json" | tee "$ROOT/diagnostics/generation-sha256.txt"

# Discover every current skinned character from the release manifest. The same
# manifest also contains motion-only fixtures explicitly named *without-skin*;
# those are recorded as non-character assets in the final summary and are not
# playback targets.
mapfile -t CHARACTER_KEYS < <(python - "$FIXTURES" "$ROOT/diagnostics/asset-classification.json" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
characters = []
non_characters = []
for key, asset in sorted(manifest["assets"].items()):
    filename = str(asset["filename"])
    if "without-skin" in filename.lower():
        non_characters.append({"key": key, "filename": filename, "reason": "motion-only fixture (without skin)"})
    else:
        characters.append({"key": key, "filename": filename})
report = {
    "schema": "motion2sheet.humanoid-motion.asset-classification",
    "version": 1,
    "manifestAssetCount": len(manifest["assets"]),
    "characterCount": len(characters),
    "characters": characters,
    "nonCharacterAssets": non_characters,
}
Path(sys.argv[2]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for item in characters:
    print(item["key"])
PY
)
test "${#CHARACTER_KEYS[@]}" -gt 0
printf '%s\n' "${CHARACTER_KEYS[@]}" | tee "$ROOT/diagnostics/character-keys.txt"

for key in "${CHARACTER_KEYS[@]}"; do
  safe_key="$(python - "$key" <<'PY'
import re, sys
value = sys.argv[1].strip().lower().replace("_", "-")
value = re.sub(r"[^a-z0-9-]+", "-", value).strip("-")
if not value:
    raise SystemExit("empty normalized character key")
print(value)
PY
  )"
  CHAR_ROOT="$ROOT/characters/$safe_key"
  mkdir -p "$CHAR_ROOT/diagnostics/character-export"

  mapfile -t ASSET < <(python - "$FIXTURES" "$key" <<'PY'
import json
import sys
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
    *) echo "mutable or unexpected fixture URL for $key: $URL" >&2; exit 1 ;;
  esac

  CHARACTER_FBX="$TMP_ROOT/${safe_key}__${FILENAME}"
  curl -fL --retry 3 --retry-delay 2 -o "$CHARACTER_FBX" "$URL"
  ACTUAL_SHA="$(sha256sum "$CHARACTER_FBX" | awk '{print $1}')"
  ACTUAL_SIZE="$(stat -c %s "$CHARACTER_FBX")"
  test "$ACTUAL_SHA" = "$EXPECTED_SHA"
  test "$ACTUAL_SIZE" -eq "$EXPECTED_SIZE"

  export key safe_key RELEASE_URL FILENAME URL EXPECTED_SHA EXPECTED_SIZE ACTUAL_SHA ACTUAL_SIZE
  python - "$CHAR_ROOT/diagnostics/release-asset-verification.json" <<'PY'
import json
import os
import sys
from pathlib import Path
report = {
    "schema": "motion2sheet.humanoid-motion.release-asset-verification",
    "version": 1,
    "assetKey": os.environ["key"],
    "outputKey": os.environ["safe_key"],
    "releaseUrl": os.environ["RELEASE_URL"],
    "filename": os.environ["FILENAME"],
    "url": os.environ["URL"],
    "expectedSha256": os.environ["EXPECTED_SHA"],
    "actualSha256": os.environ["ACTUAL_SHA"],
    "expectedSize": int(os.environ["EXPECTED_SIZE"]),
    "actualSize": int(os.environ["ACTUAL_SIZE"]),
    "sha256Pass": os.environ["EXPECTED_SHA"] == os.environ["ACTUAL_SHA"],
    "sizePass": int(os.environ["EXPECTED_SIZE"]) == int(os.environ["ACTUAL_SIZE"]),
}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  CHARACTER_DIR="$TMP_ROOT/character-$safe_key"
  motion2sheet export-character "$CHARACTER_FBX" --output "$CHARACTER_DIR"
  test -s "$CHARACTER_DIR/model.glb"
  test -s "$CHARACTER_DIR/rig.json"
  test -s "$CHARACTER_DIR/skin.json"
  cp -R "$CHARACTER_DIR/diagnostics/." "$CHAR_ROOT/diagnostics/character-export/"

  python - "$CHARACTER_DIR" "$MAPPING" "$CHAR_ROOT/diagnostics/character-mapping.json" <<'PY'
import json
import sys
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
Path(sys.argv[3]).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY

  RENDER_TMP="$TMP_ROOT/render-$safe_key"
  ANIMATION_SHA_BEFORE="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
  motion2sheet render-humanoid-animation \
    --model "$CHARACTER_DIR/model.glb" \
    --character-rig "$CHARACTER_DIR/rig.json" \
    --skin "$CHARACTER_DIR/skin.json" \
    --character-mapping "$MAPPING" \
    --animation "$ROOT/animation.json" \
    --camera-profile "$REVIEW_CAMERA" \
    --sample-count 10 \
    --output-fps 8 \
    --canvas 224x224 \
    --sheet-columns 5 \
    --render-samples 1 \
    --gif \
    --output "$RENDER_TMP"
  ANIMATION_SHA_AFTER="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
  test "$ANIMATION_SHA_BEFORE" = "$ANIMATION_SHA_AFTER"

  mv "$RENDER_TMP/pose_sheet.png" "$CHAR_ROOT/${safe_key}__pose_sheet.png"
  mv "$RENDER_TMP/preview.gif" "$CHAR_ROOT/${safe_key}__preview.gif"
  mv "$RENDER_TMP/render.json" "$CHAR_ROOT/${safe_key}__render.json"
  mkdir -p "$CHAR_ROOT/diagnostics/render"
  cp -R "$RENDER_TMP/diagnostics/." "$CHAR_ROOT/diagnostics/render/"
  rm -f "$RENDER_TMP/runtime.blend"
  printf '%s  before-render\n%s  after-render\n' "$ANIMATION_SHA_BEFORE" "$ANIMATION_SHA_AFTER" > "$CHAR_ROOT/diagnostics/render-animation-sha256.txt"
done

python tests/motion/humanoid_motion/ci/verify_authored_attack_multi_character.py \
  --root "$ROOT" \
  --fixtures "$FIXTURES" \
  --mapping "$MAPPING" \
  --output "$ROOT/summary.json"

test -s "$ROOT/animation.json"
test -s "$ROOT/summary.json"
for key in "${CHARACTER_KEYS[@]}"; do
  safe_key="${key//_/-}"
  test -s "$ROOT/characters/$safe_key/${safe_key}__pose_sheet.png"
  test -s "$ROOT/characters/$safe_key/${safe_key}__preview.gif"
  test -s "$ROOT/characters/$safe_key/${safe_key}__render.json"
  test -s "$ROOT/characters/$safe_key/${safe_key}__acceptance.json"
done

echo "Direct-authored Heavy Right Cross multi-character PASS: $ROOT"
