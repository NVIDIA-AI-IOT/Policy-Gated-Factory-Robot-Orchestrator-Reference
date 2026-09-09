# fox-openclaw

The gateway plugin — the only runtime-specific code. Registers the five floor tools
(floor_state, perceive, dispatch_task, reset_scene, verify) plus the dispatch safety policy inside an
OpenClaw runtime. Source moved here from the extension directory used by historical
branches; two path-hint strings were updated for this layout.
Wiring it against the pinned `openclaw` dependency is future work — see ../../STRUCTURE.md.
