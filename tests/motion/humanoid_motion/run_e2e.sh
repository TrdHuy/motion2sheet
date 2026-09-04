#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

ROOT="${1:-build/motion/humanoid-motion}"
FIXTURES="tests/motion/humanoid_motion/fixtures/release_assets.json"
MAPPING="profiles/humanoid_motion/mixamo_humanoid_v1.json"
CAMERA="profiles/cameras/front_humanoid_motion.json5"
CANVAS="224x224"
TMP_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TMP_ROOT="$TMP_PARENT/motion2sheet-humanoid-motion-e2e-$$"
mkdir -p "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

export ROOT FIXTURES MAPPING
rm -rf "$ROOT"
mkdir -p "$ROOT/diagnostics"
cp "$FIXTURES" "$ROOT/diagnostics/release_assets.json"

# Humanoid Motion authority and the independent oracle must stay isolated from
# source-rig/world-position authority and from the playback implementation.
! grep -R "worldPositions\|bindMatrix\|sourceBoneNames" motion2sheet/motion/humanoid_motion/schema.py
! grep -R "motion2sheet\.anim2sheet\|anim2sheet build\|Contract A" motion2sheet/motion/humanoid_motion
! grep -E "blender_export|blender_render|blender_math|build_json_scene" motion2sheet/motion/humanoid_motion/fidelity.py

download_fixture() {
  local key="$1"
  local destination="$2"
  local meta url sha size
  mapfile -t meta < <(python - "$FIXTURES" "$key" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
asset = manifest["assets"][sys.argv[2]]
print(asset["url"])
print(asset["sha256"])
print(asset["size"])
PY
  )
  url="${meta[0]}"
  sha="${meta[1]}"
  size="${meta[2]}"
  case "$url" in
    "https://github.com/TrdHuy/motion2sheet/releases/download/e2e_gh_action_asset/"*) ;;
    *) echo "mutable or unexpected fixture URL: $url" >&2; return 1 ;;
  esac
  curl -fL --retry 3 --retry-delay 2 -o "$destination" "$url"
  echo "$sha  $destination" | sha256sum -c -
  test "$(stat -c %s "$destination")" -eq "$size"
}

CHARACTER_A_FBX="$TMP_ROOT/walking_mixamo_with_skin.fbx"
MARIA_FBX="$TMP_ROOT/Maria.WProp.J.J.Ong.fbx"
WARROK_FBX="$TMP_ROOT/Warrok.W.Kurniawan.fbx"
IDLE_FBX="$TMP_ROOT/idle-without-skin.fbx"
RUN_FBX="$TMP_ROOT/run-without-skin-not-inplace.fbx"
RUN_INPLACE_FBX="$TMP_ROOT/run-without-skin-inplace.fbx"

download_fixture character-a "$CHARACTER_A_FBX"
download_fixture maria "$MARIA_FBX"
download_fixture warrok "$WARROK_FBX"
download_fixture idle "$IDLE_FBX"
download_fixture run "$RUN_FBX"
download_fixture run-inplace "$RUN_INPLACE_FBX"

motion2sheet export-character "$CHARACTER_A_FBX" --output "$ROOT/characters/character-a"
motion2sheet export-character "$MARIA_FBX" --output "$ROOT/characters/maria"
motion2sheet export-character "$WARROK_FBX" --output "$ROOT/characters/warrok"
for character in character-a maria warrok; do
  test -s "$ROOT/characters/$character/model.glb"
  test -s "$ROOT/characters/$character/rig.json"
  test -s "$ROOT/characters/$character/skin.json"
done

python - <<'PY'
import json
import os
from pathlib import Path
from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, validate_character_mapping
from motion2sheet.motion.roundtrip.schema import validate_rig_document
root = Path(os.environ["ROOT"])
mapping = json.loads(Path(os.environ["MAPPING"]).read_text(encoding="utf-8"))
ids = []
for character in ("character-a", "maria", "warrok"):
    rig = validate_rig_document(json.loads((root / "characters" / character / "rig.json").read_text(encoding="utf-8")))
    validate_character_mapping(mapping, rig)
    diagnostics = mapping_diagnostics(mapping, rig)
    assert diagnostics["leftRightVerification"]["pass"] is True
    ids.append(rig["id"])
assert len(set(ids)) == 3, ids
PY

IDLE_NORMALIZED="$TMP_ROOT/idle-normalized.fbx"
RUN_NORMALIZED="$TMP_ROOT/run-normalized.fbx"
RUN_INPLACE_NORMALIZED="$TMP_ROOT/run-inplace-normalized.fbx"
blender --background --factory-startup --python-exit-code 1 --python motion2sheet/motion/model_render/blender_prepare_motion_source.py -- --input "$IDLE_FBX" --output "$IDLE_NORMALIZED" --report "$ROOT/diagnostics/idle-normalization.json"
blender --background --factory-startup --python-exit-code 1 --python motion2sheet/motion/model_render/blender_prepare_motion_source.py -- --input "$RUN_FBX" --output "$RUN_NORMALIZED" --report "$ROOT/diagnostics/run-normalization.json"
blender --background --factory-startup --python-exit-code 1 --python motion2sheet/motion/model_render/blender_prepare_motion_source.py -- --input "$RUN_INPLACE_FBX" --output "$RUN_INPLACE_NORMALIZED" --report "$ROOT/diagnostics/run-inplace-normalization.json"
for path in "$IDLE_NORMALIZED" "$RUN_NORMALIZED" "$RUN_INPLACE_NORMALIZED"; do test -s "$path"; done

motion2sheet export-animation-json "$IDLE_NORMALIZED" --output "$ROOT/contract_b/idle"
motion2sheet export-animation-json "$RUN_NORMALIZED" --output "$ROOT/contract_b/run"
motion2sheet export-animation-json "$RUN_INPLACE_NORMALIZED" --output "$ROOT/contract_b/run-inplace"
for clip in idle run run-inplace; do
  test -s "$ROOT/contract_b/$clip/rig.json"
  test -s "$ROOT/contract_b/$clip/animation.json"
done

for clip in idle run run-inplace; do
  motion2sheet export-humanoid-animation \
    --source-rig "$ROOT/contract_b/$clip/rig.json" \
    --source-animation "$ROOT/contract_b/$clip/animation.json" \
    --mapping "$MAPPING" --id "$clip" --loop \
    --output "$ROOT/animations/$clip"
done
sha256sum "$ROOT"/animations/*/animation.json | tee "$ROOT/diagnostics/humanoid-motion-authority-sha256.txt"

for clip in idle run run-inplace; do
  motion2sheet verify-humanoid-animation-fidelity \
    --source-rig "$ROOT/contract_b/$clip/rig.json" \
    --source-animation "$ROOT/contract_b/$clip/animation.json" \
    --source-mapping "$MAPPING" \
    --animation "$ROOT/animations/$clip/animation.json" \
    --output "$ROOT/animations/$clip/diagnostics/source_humanoid_motion_fidelity.json"
done

for clip in idle run run-inplace; do
  deterministic="$TMP_ROOT/humanoid-motion-determinism-$clip"
  motion2sheet export-humanoid-animation \
    --source-rig "$ROOT/contract_b/$clip/rig.json" \
    --source-animation "$ROOT/contract_b/$clip/animation.json" \
    --mapping "$MAPPING" --id "$clip" --loop --output "$deterministic"
  cmp "$ROOT/animations/$clip/animation.json" "$deterministic/animation.json"
  rm -rf "$deterministic"
done

# Standalone playback proof: source FBX, normalized FBX and Contract B adapter
# are deliberately removed before any Humanoid Motion render occurs.
rm -f "$CHARACTER_A_FBX" "$MARIA_FBX" "$WARROK_FBX" "$IDLE_FBX" "$RUN_FBX" "$RUN_INPLACE_FBX" "$IDLE_NORMALIZED" "$RUN_NORMALIZED" "$RUN_INPLACE_NORMALIZED"
rm -rf "$ROOT/contract_b"
for path in "$CHARACTER_A_FBX" "$MARIA_FBX" "$WARROK_FBX" "$IDLE_FBX" "$RUN_FBX" "$RUN_INPLACE_FBX" "$IDLE_NORMALIZED" "$RUN_NORMALIZED" "$RUN_INPLACE_NORMALIZED" "$ROOT/contract_b"; do
  test ! -e "$path"
done

for character in character-a maria warrok; do
  for clip in idle run run-inplace; do
    motion2sheet render-humanoid-animation \
      --model "$ROOT/characters/$character/model.glb" \
      --character-rig "$ROOT/characters/$character/rig.json" \
      --skin "$ROOT/characters/$character/skin.json" \
      --character-mapping "$MAPPING" \
      --animation "$ROOT/animations/$clip/animation.json" \
      --camera-profile "$CAMERA" --frames all --canvas "$CANVAS" \
      --sheet-columns 10 --render-samples 8 --gif \
      --output "$ROOT/renders/$character/$clip"
  done
done

python tests/motion/humanoid_motion/verify_local_acceptance.py --root "$ROOT" --output "$ROOT/acceptance.json"
test ! -e "$ROOT/contract_b"
python - <<'PY'
import json
import os
from pathlib import Path
report = json.loads((Path(os.environ["ROOT"]) / "acceptance.json").read_text(encoding="utf-8"))
assert report["pass"] is True and not report["failures"]
assert report["independentCharacters"] == ["character-a", "maria", "warrok"]
assert report["proof"]["run"]["fidelity"]["locomotionStripping"]["sourceHadPlanarLocomotion"] is True
assert report["proof"]["run"]["fidelity"]["rootInvariant"]["pass"] is True
PY

echo "Humanoid Motion E2E PASS: $ROOT"
