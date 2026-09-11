# AI Animation Generator Harness

The harness is an orchestration layer between a user prompt, an AI provider,
the trusted Humanoid Motion reference library, and motion2sheet's canonical
validation/rendering code. It proves component contracts and lifecycle wiring;
it is not an animation-quality acceptance system.

## Architecture

```text
AI provider
    ^
Animation Generator Harness
    v
Humanoid Motion / motion2sheet
```

All harness implementation lives in
`motion2sheet/motion/harness_anim_generator/`. Humanoid Motion does not import
the harness, providers do not select references or own iteration policy, and
the canonical animation schema remains unchanged.

## Contracts and lifecycle

`GenerationRequest` contains `prompt`, `provider`, `output`, and
`max_iterations`. The harness deterministically selects one reference from
`sample/humanoid_motion/mixamo/`, then runs:

```text
provider candidate -> canonical validation -> render -> review
       ^                                             |
       +---------------- feedback/retry -------------+
```

Invalid candidates skip rendering and review. Failed validation and review
consume an iteration and become feedback for the next request. Reaching the
iteration limit raises a clear failure and does not publish a candidate.

Only an accepted candidate is staged and published. The public output contains
exactly:

```text
animation.json
metadata.json
preview.gif
```

Run diagnostics remain under `build/harness_anim_generator/<run-id>/`.
`metadata.json` follows the reference vocabulary: `intent`, `phases`,
`keyPoses`, `weightTransfer`, `bodyMechanics`, and `referenceUse`.

## Provider abstraction

Providers implement the `AIProvider` contract: a structured `ProviderRequest`
becomes a structured `ProviderResponse`. The POC provider runs `codex exec` in
non-interactive, ephemeral, read-only mode with JSONL and a response schema.
Generation and review use separate schemas; orchestration decisions remain in
the harness.

## Local usage

Install/authenticate Codex CLI and make Blender available on `PATH`, then run:

```bash
motion2sheet generate-humanoid-animation \
  --prompt "Tạo một heavy spinning attack" \
  --provider codex-cli \
  --max-iterations 3 \
  --output build/generated/spinning-attack
```

The renderer bootstraps a test character from the tracked
`sample/walk_mixamo.fbx` and reuses the existing Humanoid Motion renderer. The
output path must be absent or empty; existing artifacts are never overwritten.

## Test philosophy

Automated tests use fake providers, adapters, and reviewers plus mocked
subprocess calls. They verify prompt propagation, retry feedback, validation
gating, iteration limits, final packaging, reference discovery, and CLI/CI
routing. They never call a real AI provider, use credentials, run Blender,
generate a demo animation, or judge animation quality.
