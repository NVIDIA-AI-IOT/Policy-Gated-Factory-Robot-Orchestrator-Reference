# Floor operating playbook

<!-- Maintained source for ops/sync-playbook.sh and the MCP server's instructions.
     Edit this file, then synchronize installed copies through the deployment tools. -->

## Floor operating rule

Run actions one at a time. Wait for each result and fresh visual evidence before
continuing. Independent `dispatch_task` calls must remain serial.

When explicitly enabled, `dispatch_parallel` executes one validated left/right
pair. Two independent policy servers process one arm each, using the same
GR00T checkpoint. Both `tote` and `tote_r` need separate visual verification.
Reconcile an unverified dispatch with `floor_state`; do not repeat it blindly.

### Certified dual-arm GR00T serial fallback

For the six-object scene (`groot_three_object`, layout `3/3`, seed `31302`),
use this serial pick-and-place order. The MCP guard enforces it when
`PGFR_CERTIFIED_GROOT_ORDER=1` and mixed mode is inactive:

1. `franka_right`: green brick, `conveyor_2` → `tote_green`; verify `tote_r`.
2. `franka_left`: green brick, `conveyor_1` → `tote_green`; verify `tote`.
3. `franka_right`: red cube, `conveyor_2` → `tote_red`; verify `tote_r`.
4. `franka_left`: red cube, `conveyor_1` → `tote_red`; verify `tote`.
5. `franka_right`: blue cylinder, `conveyor_2` → `tote_blue`; verify `tote_r`.
6. `franka_left`: blue cylinder, `conveyor_1` → `tote_blue`; verify `tote`.

Do not group all colors on one arm or reorder this certified sequence. Each
move is a separate MCP `dispatch_task` call and its fresh visual proof must
clear before the next move. After all six moves verify, haul `tote`, verify it
on `rack_1`, then haul `tote_r` and verify both totes on `rack_1`.

The optional concurrent reference is not the serial order grouped by color.
When `certified_groot_sequence` reports `execution_mode` =
`concurrent_mixed_pairs`, follow its three transactions exactly:

1. left blue + right green; verify blue in `tote` and green in `tote_r`;
2. left green + right red; verify green in `tote` and red in `tote_r`;
3. left red + right blue; verify red in `tote` and blue in `tote_r`.

That plan is exposed only when certified-order enforcement is active and the
deployment has explicitly enabled both parallel and flexible-order
capabilities after the two-server B=1 readiness gate. Never substitute the
failed same-color green/red/blue grouping. If the capability report remains
`serial_fallback`, use the six serial calls above unchanged.

### Arm selection for whole-cell requests

For a vague whole-cell instruction such as "check the table and put the blocks
in their matching totes," use **both arms by default**; do not ask the operator
to restate the mission. In the hardened layout-3 scene, prefer the three
exact mixed `dispatch_parallel` transactions returned by
`certified_groot_sequence` when its mixed capability is enabled. Otherwise
use the six certified serial moves above.

An explicit arm-count instruction overrides only that default:

- "use both arms" / "use two arms" uses the bounded two-arm behavior above.
- "use only the left arm" sorts only the three local left-side objects from
  `conveyor_1` into `tote`, using serial `dispatch_task` calls and left-tote
  visual proof after each move.
- "use only the right arm" sorts only the three local right-side objects from
  `conveyor_2` into `tote_r`, using serial `dispatch_task` calls and right-tote
  visual proof after each move.
- "use one arm" without naming left or right is the only arm-selection case
  that requires a clarification before motion: ask which arm.

Never make a single arm reach across the cell for the other arm's local object
set, and never silently activate the idle arm after the operator requested one
arm. If the operator names different colors for the two arms and says
"together," use the mixed-color transaction described below.

### Explicit mixed-order evaluation

`PGFR_GROOT_FLEXIBLE_ORDER=1` does not enable motion by itself. In the certified
mission it combines with `PGFR_GROOT_PARALLEL_ENABLED=1` to select the exact
three-pair Order744 plan above; the MCP state machine rejects skipped,
reversed, partial, or serialized pairs. Preserve its barriers: each
`dispatch_parallel(left_color, right_color)` result and both identity-bound
visual proofs must clear before continuing. All endpoint/source/destination
validation, physics verification, guarded recovery, zone checks, and per-arm
visual verification remain mandatory. Arbitrary flexible order is not exposed by
this route.

`certified_groot_sequence` is the authoritative runtime capability report. If
its `active_capabilities.mixed_color_parallel_enabled` value is `true`, call
the exact `transactions` it returns. Do not ask the operator to edit environment
variables, do not describe this as bypassing a guard, and do not
substitute serial or same-color moves. If the tool refuses, quote its exact
returned reason; never infer that a flag is disabled from an unrelated
lower-layer error.

## Objects and endpoints

- Each arm starts with a red cube, a blue cylinder, and a green brick: six
  objects in total. `franka_left` uses `conveyor_1`; `franka_right` uses
  `conveyor_2`. Each dispatch moves one object.
- The left tote is `tote`; the right tote is `tote_r`. Each has compartments
  named `tote_red`, `tote_blue`, and `tote_green` in move requests. The selected
  arm determines which physical tote receives the object.
- `mobilebot` is the AMR with a third arm. It hauls the totes separately to
  `rack_1`, side-by-side on the lowest shelf.

Use fresh symbolic state for exact object counts. Camera frames show limited
regions, and the two sets contain identical colors and shapes. Do not treat a
partial view as a count of the entire cell.

## Tools and cameras

- `floor_state` returns simulator state and endpoint identities.
- `perceive(target)` returns the configured VLM's observation. In fused mode,
  it also includes symbolic state and discrepancy fields; symbolic state
  remains authoritative when the two disagree. In `vision_only` mode,
  `perceive` omits symbolic object state. The physical result checks are unchanged.
- `dispatch_task` requests one policy-checked floor action.
- `dispatch_parallel` requests only the next enabled pair returned by
  `certified_groot_sequence`; it is not a general parallel scheduler.
- `verify(predicate, region)` checks a specific visual claim. Only `yes` clears
  the required visual evidence; `no` and `unknown` leave it unresolved.
- `reset_scene` is an operator recovery action. Use it only on an explicit
  reset request, when the cell is idle, and require `verified:true`.

| Region | View |
|---|---|
| `conveyor_1` | Left objects on the conveyor area |
| `conveyor_2` | Right objects on the conveyor area |
| `table_1` | Wide overhead view of both sorting stations and totes |
| `tote` | Left tote compartments |
| `tote_r` | Right tote compartments |
| `rack_1` | Receiving shelf |

For a whole-cell survey, inspect `conveyor_1`, `conveyor_2`, `table_1`, and
`rack_1`. Add tote close-ups for placement verification. Tote and conveyor
views may share a camera pose, so they are not independent views of the cell.

## Dispatch and recovery

Use the tool's argument schema:

- Sort an object with `move`, supplying the arm, `color`, `source`, and
  `destination=tote_<color>`.
- Haul the left tote with `pick_and_place`, `endpoint=mobilebot`,
  `object_id=tote`, and `target_id=rack_1`.
- Haul the right tote with the same action and `object_id=tote_r`, after the
  first haul and its rack verification finish.

Outside the reference GR00T sequence, use the nearest eligible arm for the
requested object. In the reference scene, preserve the endpoint and order
reported by `certified_groot_sequence`.

After each dispatch, read the physical result and verify the exact object at
its destination. An unverified result does not mean nothing moved. Reconcile
it with `floor_state` and destination/source evidence before further motion.
The guarded MCP path permits at most one additional move attempt after visual
proof that the exact object remains at its source. Do not switch endpoints or
repeat an uncertain action. If the object cannot be located, or required visual
evidence remains `no` or `unknown`, stop and report the returned reason.

## Interpreting goals and reporting completion

- “Sort the objects” means move each requested object to its matching tote
  compartment, following the arm-selection and ordering rules above.
- “Only the red ones” or “everything but green” restricts the object set; it
  does not authorize changing the allowed action order.
- “Shelve the tote” means haul the named tote and verify it on `rack_1`.
- “Sort and shelve both totes” means sort the objects, then haul and verify
  each tote separately. Include both totes even if one starts empty.
- For an ambiguous object, arm, or destination, inspect the scene first. Ask
  the operator if the ambiguity remains or the request conflicts with policy.

Before reporting a full sort-and-shelve mission complete, check that no
requested objects remain on the conveyor, both totes are on `rack_1`, and each
placement has the required physical and visual evidence. For narrower requests,
check only the requested result. Report missing evidence or unfinished steps
explicitly; a successful model response is not mission completion.
