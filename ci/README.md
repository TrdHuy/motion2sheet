# Dependency-aware CI

`components.json` is the source of truth for static component ownership and static test-target dependencies. Profile-driven animation clip targets are intentionally dynamic: `detect_affected.py` discovers valid directories under `profiles/anim2sheet/animations/*` and synthesizes their canonical unit/E2E targets without per-clip manifest entries.

On pull requests, `detect_affected.py` maps changed paths to directly affected components/targets, expands reverse dependencies, and runs only the affected unit/E2E targets. A change limited to one animation profile directory selects that clip without pulling another animation E2E; anim common/core changes fan out to every discovered clip. Unknown non-ignored paths fail safe to the full test graph.

On pushes to `master` and manual workflow dispatches, CI runs the complete graph, including every currently discovered valid animation clip.

Motion production code has one canonical feature surface under `motion2sheet/motion/`; there are no legacy top-level motion facades. Motion output-mode behavior is owned by `motion/output` and exercised by its own unit/E2E targets. Sprite-generation skills and samples are owned by the lightweight `sprite-workflow` component, so prompt/skill-only changes do not require Blender regression. `vfx2sheet` keeps its existing feature/effect architecture and is only mapped into this dependency graph.
