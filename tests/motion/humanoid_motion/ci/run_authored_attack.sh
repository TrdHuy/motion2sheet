#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

ROOT="${1:-build/motion/humanoid-motion/direct-authored-attack}"
FIXTURES="tests/motion/humanoid_motion/fixtures/release_assets.json"
MAPPING="profiles/humanoid_motion/mixamo_humanoid_v1.json"
CAMERA="profiles/cameras/front_humanoid_motion.json5"
GENERATOR="samples/humanoid_motion/animations/right-overhand-smash/generate.py"
COMMITTED="samples/humanoid_motion/animations/right-overhand-smash/animation.json"
TMP_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TMP_ROOT="$TMP_PARENT/motion2sheet-authored-attack-$$"
mkdir -p "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

rm -rf "$ROOT"
mkdir -p "$ROOT/diagnostics"

GEN_A="$TMP_ROOT/generation-a.json"
GEN_B="$TMP_ROOT/generation-b.json"
python "$GENERATOR" --output "$GEN_A"
python "$GENERATOR" --output "$GEN_B"
cmp "$GEN_A" "$GEN_B"
cmp "$GEN_A" "$COMMITTED"
cp "$COMMITTED" "$ROOT/animation.json"
sha256sum "$GEN_A" "$GEN_B" "$COMMITTED" "$ROOT/animation.json" | tee "$ROOT/diagnostics/generation-sha256.txt"

mapfile -t ASSET < <(python - "$FIXTURES" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
asset = manifest["assets"]["warrok"]
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
  *) echo "mutable or unexpected fixture URL: $URL" >&2; exit 1 ;;
esac

CHARACTER_FBX="$TMP_ROOT/$FILENAME"
curl -fL --retry 3 --retry-delay 2 -o "$CHARACTER_FBX" "$URL"
ACTUAL_SHA="$(sha256sum "$CHARACTER_FBX" | awk '{print $1}')"
ACTUAL_SIZE="$(stat -c %s "$CHARACTER_FBX")"
test "$ACTUAL_SHA" = "$EXPECTED_SHA"
test "$ACTUAL_SIZE" -eq "$EXPECTED_SIZE"

export RELEASE_URL FILENAME URL EXPECTED_SHA EXPECTED_SIZE ACTUAL_SHA ACTUAL_SIZE
python - "$ROOT/diagnostics/release-asset-verification.json" <<'PY'
import json
import os
import sys
from pathlib import Path
report = {
    "schema": "motion2sheet.humanoid-motion.release-asset-verification",
    "version": 1,
    "assetKey": "warrok",
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

CHARACTER_DIR="$TMP_ROOT/character"
motion2sheet export-character "$CHARACTER_FBX" --output "$CHARACTER_DIR"
test -s "$CHARACTER_DIR/model.glb"
test -s "$CHARACTER_DIR/rig.json"
test -s "$CHARACTER_DIR/skin.json"
mkdir -p "$ROOT/diagnostics/character-export"
cp -R "$CHARACTER_DIR/diagnostics/." "$ROOT/diagnostics/character-export/"

python - "$CHARACTER_DIR" "$MAPPING" "$ROOT/diagnostics/character-mapping.json" <<'PY'
import json
import sys
from pathlib import Path
from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, read_mapping, validate_character_mapping
from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import validate_skin_document

character = Path(sys.argv[1])
mapping_path = Path(sys.argv[2])
rig = validate_rig_document(read_json(character / "rig.json"))
mapping = validate_character_mapping(read_mapping(mapping_path), rig)
validate_skin_document(read_json(character / "skin.json"), rig)
report = mapping_diagnostics(mapping, rig)
assert report["leftRightVerification"]["pass"] is True
Path(sys.argv[3]).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
PY

ANIMATION_SHA_BEFORE="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
motion2sheet render-humanoid-animation \
  --model "$CHARACTER_DIR/model.glb" \
  --character-rig "$CHARACTER_DIR/rig.json" \
  --skin "$CHARACTER_DIR/skin.json" \
  --character-mapping "$MAPPING" \
  --animation "$ROOT/animation.json" \
  --camera-profile "$CAMERA" \
  --sample-count 8 \
  --output-fps 8 \
  --canvas 192x192 \
  --sheet-columns 8 \
  --render-samples 1 \
  --gif \
  --output "$ROOT/render"
ANIMATION_SHA_AFTER="$(sha256sum "$ROOT/animation.json" | awk '{print $1}')"
test "$ANIMATION_SHA_BEFORE" = "$ANIMATION_SHA_AFTER"
printf '%s  before-render\n%s  after-render\n' "$ANIMATION_SHA_BEFORE" "$ANIMATION_SHA_AFTER" > "$ROOT/diagnostics/render-animation-sha256.txt"

python tests/motion/humanoid_motion/ci/verify_authored_attack.py \
  --animation "$ROOT/animation.json" \
  --committed-animation "$COMMITTED" \
  --generation-a "$GEN_A" \
  --generation-b "$GEN_B" \
  --asset-verification "$ROOT/diagnostics/release-asset-verification.json" \
  --character-dir "$CHARACTER_DIR" \
  --mapping "$MAPPING" \
  --render-dir "$ROOT/render" \
  --output "$ROOT/acceptance.json"

test -s "$ROOT/animation.json"
test -s "$ROOT/render/pose_sheet.png"
test -s "$ROOT/render/preview.gif"
test -s "$ROOT/render/render.json"
test -d "$ROOT/render/diagnostics"
test -s "$ROOT/acceptance.json"

echo "Direct-authored Humanoid attack PASS: $ROOT"
