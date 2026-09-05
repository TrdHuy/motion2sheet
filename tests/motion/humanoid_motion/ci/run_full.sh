#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$REPO_ROOT"

bash tests/motion/humanoid_motion/ci/run_e2e.sh "${1:-build/motion/humanoid-motion}" full
