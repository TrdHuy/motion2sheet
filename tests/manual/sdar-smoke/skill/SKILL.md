# SDAR Manual Smoke Test

This skill verifies the production SDAR runtime plumbing without performing an
animation workflow. Work only inside the current run workspace. Do not modify
the repository, run Blender, or invoke the Humanoid Motion authoring workflow.

Run one iteration and report its lifecycle through `sdar-notify`.

## Step: create-note

1. Report `skill-start create-note` for the current iteration.
2. Create `note.txt` in the current run workspace with a short smoke-test note.
3. Report `artifact-created note.txt` for the current iteration.
4. Report `skill-complete create-note` with a short summary.

## Step: finalize

1. Report `skill-start finalize` for the current iteration.
2. Create these non-empty smoke-test files inside `final/`:
   - `animation.json`
   - `metadata.json`
   - `preview.gif`
3. The files only exercise the generic output contract. They do not need to
   represent a real animation, metadata analysis, or rendered preview.
4. Report `skill-complete finalize` with a short summary.
5. Report `iteration-complete` for the current iteration.
6. Report completion with `sdar-notify complete`, declaring all three paths.

Before the first step, report `iteration-start 1` with a smoke-test reason.
