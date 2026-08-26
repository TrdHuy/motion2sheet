# Dependency-aware CI

`components.json` is the source of truth for component ownership and test-target dependencies.

On pull requests, `detect_affected.py` maps changed paths to directly affected components, expands reverse dependencies, and runs only the affected unit/E2E targets. Unknown non-ignored paths fail safe to the full test graph.

On pushes to `master` and manual workflow dispatches, CI runs the complete graph.

Motion production code has one canonical feature surface under `motion2sheet/motion/`; there are no legacy top-level motion facades. Motion output-mode behavior is owned by `motion/output` and exercised by its own unit/E2E targets. `vfx2sheet` keeps its existing feature/effect architecture and is only mapped into this dependency graph.
