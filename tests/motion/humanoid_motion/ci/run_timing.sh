#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

# Source-native timing is authority. This suite includes FBX/BVH timing and the
# wrong-imported-FPS fail-closed regression.
pytest tests/motion/roundtrip/test_contract.py
