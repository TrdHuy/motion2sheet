# Skill-Driven Animation Agent Runtime

The animation generator is a Skill-Driven Agent Runtime (SDAR). Its purpose is
to supervise an autonomous authoring agent and preserve what happened during a
run. It is not an animation planner, renderer, reviewer, or quality gate.

The responsibility model is deliberately narrow:

- **Skill = workflow authority.** The complete committed
  `skills/humanoid-motion-local-authoring/SKILL.md` is passed verbatim to the
  agent. Its neighboring `skill.json` lists observable workflow steps but is
  not an animation schema.
- **Agent = domain owner.** The agent interprets intent, inspects the repo,
  selects references, authors and reviews motion, invokes motion2sheet,
  iterates, validates, and creates all final artifacts.
- **Harness / SDAR = runtime supervisor and event/history/artifact
  aggregator.** It launches the process, accepts events, tracks liveness,
  persists observations, and collects declared output files.
- **Report = observability surface.** It renders normalized runtime state and
  never infers animation quality.

In short: **Harness launches. Agent executes. Agent pushes. Harness observes.
Report reflects.** Humanoid Motion never imports the harness, and the harness
does not import or reproduce Humanoid Motion domain operations.

## Input and output contracts

The public request contains a user `prompt`, `provider`, `output`, optional
`resume_run_id`, and report options. Users do not select references, key poses,
mechanics, metadata, or domain iterations.

An accepted run publishes exactly:

```text
<output>/
├── animation.json
├── metadata.json
└── preview.gif
```

The agent declares these paths with `agent.completed`. Only after that event is
processed, the process exits with code zero, and the event queue drains does
the harness check the generic file contract: each file must be a readable,
non-empty regular file inside the agent workspace. The harness does not parse
animation or metadata semantics and does not inspect the GIF for quality.

## Agent runtime and asynchronous events

Providers implement `AgentProvider.start(AgentRunRequest) -> AgentSession`.
The request contains the prompt, full skill text, skill manifest, optional
read-only history, repository/workspace locations, and event ingress details.
The Codex CLI provider launches non-interactive `codex exec --json` as a local
agent; it does not request one immediate generated JSON response.

Every run binds a local-only endpoint:

```text
POST http://127.0.0.1:<port>/runs/<run-id>/events
Authorization: Bearer <per-run-token>
```

The HTTP handler authenticates and validates an envelope, deduplicates its
`eventId`, enqueues it, and returns `202 Accepted`. A separate FIFO processor
persists the event, reduces run/skill/iteration state, snapshots safe declared
artifacts and evidence, then publishes to SSE. Disk work and slow report
clients cannot block the sender. Agent `sequence` applies only to the
`agent_push` stream; the harness assigns the authoritative monotonic
`receiveOrder` across `agent_push`, `provider`, and `harness` provenance.

The runtime provides `sdar-notify` so the agent reports semantic intent without
constructing HTTP envelopes. The helper supplies IDs, timestamps, sequence,
authorization, and retry/backoff. `HARNESS_RUN_ID`, `HARNESS_EVENT_URL`,
`HARNESS_TOKEN`, and `SDAR_NOTIFY` are available to commands run by the agent.
The runtime instruction requires the agent to bracket its self-selected
iterations and applicable manifest steps with the corresponding start,
complete, or skip notifications, then declare final output paths. This is a
telemetry protocol, not a domain workflow or quality gate.

Codex runs with the current run's agent directory as its working directory and
only writable workspace. The repository and imported resume history remain
read-only context. Agent shell commands receive an explicit runtime allowlist
rather than unrelated host credentials; provider credentials needed by the
parent Codex process are not automatically inherited by those commands. The
per-run token remains in memory/environment and all disk/report sinks redact an
accidental echo.

Skill steps are tracked per iteration as `not_started`, `in_progress`,
`completed`, or `skipped`. Harness observes whether steps were reported or
executed, but does not determine whether those steps were performed correctly.
Missing, skipped, or unknown steps are diagnostic information and never an
animation acceptance gate.

## History, paths, and reporting

Run data is retained below `build/harness_anim_generator/<run-id>/`, including
normalized and provider logs, iteration history, safe artifact/evidence
snapshots, archival finals, and a static report. Declared paths are resolved
inside the agent workspace; traversal, host absolute paths, and symlink escape
are rejected for copy, snapshot, publish, and HTTP serving. An outside
`artifact.read` remains observation text and is never exposed.

`--resume-run OLD_RUN_ID` creates a new run ID with `parentRunId=OLD_RUN_ID`.
It imports the old run as read-only history and never mutates or appends an
iteration to the old workspace. Iterations are versions inside one execution;
resume is a new execution.

The CLI prints the realtime report URL immediately. The page receives the same
processed event stream through Server-Sent Events and shows run/liveness,
skill progress, current and previous iterations, activity, artifacts, and
evidence. A generic harness ticker emits `runtime.liveness.changed` through the
same FIFO pipeline when an otherwise silent live process becomes idle or
possibly stalled, so the report remains event-driven without polling the
agent. Once the server stops, `report/index.html` remains reviewable.

## Local usage

```bash
motion2sheet generate-humanoid-animation \
  --prompt "Hãy tạo một animation tấn công cho swordsman" \
  --provider codex-cli \
  --output build/generated/swordsman-attack
```

Use `--report-port` to request a port, `--no-open-report` to disable browser
opening, and `--resume-run` to seed a new run from old history. The default
skill path is committed and not a mandatory CLI argument; a missing or invalid
`SKILL.md` or `skill.json` fails before agent launch.

## Test philosophy

Automated tests use fake agent providers/sessions and fake HTTP push clients.
They verify asynchronous ingestion, ordering, idempotency, liveness, history,
redaction, path confinement, report/SSE behavior, terminal semantics, and
generic output packaging. They never call Codex or another AI service, use
credentials, run Blender, generate a demo animation, or judge animation
quality.
