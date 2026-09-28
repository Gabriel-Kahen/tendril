# Working on Tendril

- Read `README.md`, `docs/HANDOFF.md`, and the relevant design documents before substantive changes.
- This is now a runnable research implementation. Distinguish implemented features, measured fixtures, and unproven evolutionary or guidance advantages. Read docs/IMPLEMENTATION.md for physical conventions and limits.
- Keep growth, mechanics, collisions, and evaluation genuinely 3D from the outset.
- Preserve the purpose: discover diverse, coherent physical organisms through development, novelty, and local capability. Do not silently replace it with a single-task optimizer.
- Reuse the selected MuJoCo backend and preserve the documented physical feasibility checks.
- Jev selects every evolutionary candidate. No unguided/adaptive search mode or random fallback is supported. Missing credentials or guidance failures stop the run with resumable state. Simulation, not Jev, supplies survival evidence.
- Distinguish accepted decisions, tentative proposals, and measured results. Challenge unsupported assumptions and communicate concisely.
- Keep code small and inspectable. Log versions, seeds, edits, physical accounting, and experiment configurations needed for replay.
- Proceed with routine authorized work without repeated approval requests. Use parallel agents when useful for concrete independent subtasks.
- Never commit credentials, private conversation dumps, generated bulk runs, or unrelated personal files.
