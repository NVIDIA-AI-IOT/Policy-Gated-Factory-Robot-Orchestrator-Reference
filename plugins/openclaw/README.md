# fox-openclaw

The gateway plugin — the only runtime-specific code. Registers the five floor tools
(floor_state, perceive, dispatch_task, reset_scene, verify) plus the dispatch safety policy inside an
OpenClaw runtime. Source moved here from `extensions/industrial-claw-floor/`
(two path-hint strings updated for the new layout; on `main`/`fox-brain-restructure` it still lives at `extensions/industrial-claw-floor/` for the vendored-runtime demo).
Wiring it against the pinned `openclaw` dependency is future work — see ../../STRUCTURE.md.
