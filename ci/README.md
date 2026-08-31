# Central affected CI

`ci/components.json` defines static component ownership and reusable test targets. `ci/detect_affected.py` adds data-driven Anim2Sheet clip targets at runtime.

## Anim2Sheet Profile Contract v2 discovery

A canonical animation clip is discovered from `profiles/anim2sheet/animations/<clip>/` when the directory contains both required profile files:

```text
animation.json5
motion.json
```

A directory containing only one required file fails closed instead of being silently ignored. No clip name is registered in `ci/components.json` or `.github/workflows/ci.yml`.

Affected behavior:

- clip profile-only change -> that clip E2E (and its unit target if that test directory exists)
- `anim-common`, rig, character, or camera change -> every discovered animation clip
- `anim-core` change -> every discovered animation clip
- full/global CI -> every discovered animation clip
- unrelated VFX-only change -> no animation E2E
- unmapped paths -> fail-safe full CI

This keeps `motion.json` + `animation.json5` as the canonical future importer output contract without a CI whitelist step.
