# Upgrade after the full-form product rename

This guide covers an existing installation that used the full-form
`Industrial Claw` names and is moving to **Policy-Gated Factory Robot
Orchestrator Reference**. This is a maintenance-window upgrade, not an
in-place hot reload. Stop both hosts before changing paths or installed files.

The rename deliberately preserves the abbreviated compatibility surface:
`IC_*` environment variables, `ic-*` services and containers, `ic_*` Python
packages other than the main IC Spine package, and `/ic/*` ROS topics and
schemas do not change.

The two published Hugging Face identifiers also do not change:

- `mmallick/industrial-claw-groot-order744-cont24`
- `mmallick/industrial-claw-groot-order744-cont24-dataset`

Those strings identify external repositories. Do not replace them in an
environment file, model manifest, cache metadata, or downloaded snapshot.

## What changes

| Legacy name or default | New name or default | Action |
|---|---|---|
| `industrial_claw` Python distribution, import, and executable | `policy_gated_factory_robot_orchestrator_reference` | Recreate the IC Spine environment and update callers. There is no compatibility alias. |
| `reference/industrial-claw/` | `reference/policy-gated-factory-robot-orchestrator-reference/` | Use the new checkout; do not retain scripts that point into the old source tree. |
| `servers/industrial-claw-mcp/` | `servers/policy-gated-factory-robot-orchestrator-reference-mcp/` | Recreate the MCP virtual environment and update MCP client commands. The executable remains `ic-mcp`. |
| `skills/industrial-claw-orchestrator/` | `skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/` | Re-run `ops/sync-playbook.sh` after installation. |
| `~/.industrial_claw/` | `~/.policy_gated_factory_robot_orchestrator_reference/` | Move CLI run and mock floor-state data if it must be retained. |
| `~/.industrial-claw/openclaw/` | `~/.policy-gated-factory-robot-orchestrator-reference/openclaw/` | Move the OpenClaw workspace while its services are stopped, then regenerate `openclaw.json` from the new template and reapply reviewed provider settings. |
| `~/industrial-claw-models/` | `~/policy-gated-factory-robot-orchestrator-reference-models/` | Move or restore the verified model tree and Hugging Face cache as one tree. |
| `~/.local/lib/industrial-claw/` | `~/.local/lib/policy-gated-factory-robot-orchestrator-reference/` | Reinstall the simulation-host bridge; do not copy the generated helper forward. |
| A checkout such as `~/industrial-claw/` | `~/Policy-Gated-Factory-Robot-Orchestrator-Reference/` | Use a clean checkout of the exact release commit. Rerender every path-bound unit. |

The following locations keep their current names: `~/.config/ic-spine/`,
`~/.local/share/ic-spine/`, `~/.openclaw/secrets.env`, `~/ic-journal/`,
`~/groot_shadow/Isaac-GR00T/`, and the `ic-*` user-unit names. They still need
to be backed up and inspected because their contents can refer to the old
checkout, package, model, or OpenClaw paths.

Do not rename an existing Isaac scripts mount while a container is using it.
Prepare a fresh exact mount with `ops/isaac-sim-workstation.sh --prepare` for
the scripted baseline, or reinstall the learned-policy cell with
`ops/install-groot-cell.sh` after Isaac Sim is stopped.

## 1. Record the deployment and stop both hosts

Choose and record the exact published commit or tag before starting. The
historical 2026-09-08 mission accepted the pre-rename tree; it is evidence for
that snapshot, not live acceptance of the renamed tree. The renamed release
candidate requires the clean-install and upgrade validation below.

Record the enabled state and current revisions on each host:

```bash
git -C "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference" status --short --branch
git -C "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference" rev-parse HEAD
systemctl --user list-unit-files 'ic-*'
systemctl --user list-units --all 'ic-*'
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
```

If the legacy checkout has another path, substitute it in the two Git
commands. Save the output with the change record. Confirm that no mission,
reset, physical action, model request, or evidence write is in flight.

On Thor, explicitly stop every owner that can use a path being migrated:

```bash
systemctl --user stop \
  ic-console.service ic-chat.service ic-workflows.service \
  ic-openclaw.service ic-seam.service ic-gpu-exporter.service \
  ic-perception-vlm.service \
  ic-groot-relay@shared-left.service \
  ic-groot-relay@shared-right.service \
  ic-groot-policy@shared-left.service \
  ic-groot-policy@shared-right.service \
  ic-groot-shared-stack.target
```

On the simulation host, stop the bridge and then explicitly stop the known
Isaac container selected for this deployment:

```bash
systemctl --user stop ic-groot-two-host-bridge.service
docker ps --format '{{.Names}}' | grep -E '^(isaac-sim|ic-isaac-sim-baseline)$' || true
# After confirming the exact target above, stop that named container, for example:
docker stop isaac-sim
```

Do not identify or terminate an arbitrary process only by port number. Verify
that all listed user units are inactive and that no container is using the
scripts mount before continuing.

## 2. Back up configuration and persistent data

Use an encrypted, access-controlled host snapshot when available. At minimum,
create a mode-0700 backup outside both the checkout and the directories being
migrated. Back up these items without printing their contents:

- `~/.config/ic-spine/` and `~/.config/systemd/user/ic-*`
- `~/.openclaw/secrets.env`
- `~/.industrial_claw/` and `~/.industrial-claw/`, when present
- `~/.local/share/ic-spine/` and `~/ic-journal/`
- `~/industrial-claw-models/`
- the simulation-host bridge configuration and external Isaac/GR00T state
- the old checkout's revision, dirty-file list, and any operator-owned changes

Model weights and Isaac caches can be large. A same-filesystem rename is not a
backup; keep a verified snapshot or a second copy until the upgraded mission
passes. Preserve ownership, modes, symbolic links, and extended attributes.
The backup contains credentials and mission evidence, so restrict it to the
deployment owner.

Set `UPGRADE_BACKUP` to the verified backup directory on the current host. Do
not use a directory inside either checkout or any path in the migration table:

```bash
export UPGRADE_BACKUP=/absolute/path/to/restricted-upgrade-backup
test -d "$UPGRADE_BACKUP"
test -O "$UPGRADE_BACKUP"
test "$(stat -c '%a' "$UPGRADE_BACKUP")" = 700
```

## 3. Install the exact new checkout

Prefer a clean, side-by-side checkout over renaming the directory beneath
existing virtual environments. Replace the placeholder with the published
40-character release commit and verify a clean tree:

```bash
cd "$HOME"
test ! -e "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
git clone \
  https://github.com/NVIDIA-AI-IOT/Policy-Gated-Factory-Robot-Orchestrator-Reference.git
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
git checkout --detach REPLACE_WITH_PUBLISHED_COMMIT
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

If the legacy deployment already occupies that canonical checkout path, move
the complete stopped checkout into the restricted backup first, or choose a
separate reviewed path for the new clone and use that path consistently. Do
not pull the breaking rename over the working tree beneath existing virtual
environments or rendered units.

Do not use a moving branch or `HEAD` as the release identity. Keep the old
checkout and its backup read-only until rollback is no longer required.

## 4. Migrate state and audit preserved environment files

Move a legacy directory only when the destination does not exist. Never merge
two state trees with a recursive copy. With the relevant services stopped and
a verified backup available, migrate the three full-form persistent roots that
exist on the host:

```bash
if [ -e "$HOME/.industrial_claw" ]; then
  test ! -e "$HOME/.policy_gated_factory_robot_orchestrator_reference"
  mv -- "$HOME/.industrial_claw" \
    "$HOME/.policy_gated_factory_robot_orchestrator_reference"
fi
if [ -e "$HOME/.industrial-claw" ]; then
  test ! -e "$HOME/.policy-gated-factory-robot-orchestrator-reference"
  mv -- "$HOME/.industrial-claw" \
    "$HOME/.policy-gated-factory-robot-orchestrator-reference"
fi
if [ -e "$HOME/industrial-claw-models" ]; then
  test ! -e "$HOME/policy-gated-factory-robot-orchestrator-reference-models"
  mv -- "$HOME/industrial-claw-models" \
    "$HOME/policy-gated-factory-robot-orchestrator-reference-models"
fi
```

If a destination already exists, stop and compare it against the backup; do
not overwrite or combine it. Verify the model tree after moving it:

```bash
ops/verify-groot-models.sh \
  "$HOME/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24"
```

The bootstrap preserves existing operator environment files instead of
overwriting them. Audit the preserved files before reinstalling:

```bash
rg -n 'Industrial Claw|industrial_claw|industrial-claw' \
  "$HOME/.config/ic-spine" "$HOME/.config/systemd/user" || true
```

Update old checkout, import/executable, model, source, patch, OpenClaw, and
bridge-helper paths. In particular, IC Chat and OpenClaw must converge on:

```dotenv
IC_OPENCLAW_CONFIG=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json
OPENCLAW_STATE_DIR=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw
OPENCLAW_CONFIG_PATH=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json
```

Do not change an `IC_*`, `ic-*`, `/ic/*`, or `ic_*` compatibility identifier
merely because it contains `ic`. Do not change either published
`mmallick/industrial-claw-groot-order744-cont24` Hugging Face identifier. Treat
any other remaining full-form legacy value as an item that requires explicit
review, not an invitation to run a repository-wide substitution.

The migrated OpenClaw `openclaw.json` can contain an absolute command path to
the former MCP directory. Preserve a copy, then move that one generated config
out of the live state tree so the new launcher can seed its complete template:

```bash
OPENCLAW_CONFIG="$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json"
test ! -e "$UPGRADE_BACKUP/openclaw.json.pre-rename"
test ! -e "$OPENCLAW_CONFIG" || \
  mv -- "$OPENCLAW_CONFIG" "$UPGRADE_BACKUP/openclaw.json.pre-rename"
```

Do not copy the complete old JSON back: that would restore the stale MCP
command. After the new file is seeded, compare it with the backup and reapply
only reviewed provider/model customizations through the supported OpenClaw
configuration interface.

Archive generated readiness records so a pre-upgrade success cannot satisfy a
post-upgrade check. On Thor, move `shared-left.json` and `shared-right.json`
from `~/.local/share/ic-spine/groot/` into the backup. On the simulation host,
move the same two files from
`~/.local/share/ic-spine/groot/remote-thor-v36/`, plus
`~/.config/ic-spine/groot-two-host-bridge.env` and the generated
`~/.local/lib/industrial-claw/` helper directory, into that host's backup.
Keep mission journals, Chat sessions, and evidence in place; they are
persistent records, not readiness signals.

## 5. Recreate environments and rerender installed files

Python virtual environments embed absolute interpreter and editable-source
paths. Do not reuse or copy an environment from the old checkout. A clean new
checkout starts without repository-owned `.venv` directories, and the frozen
bootstrap recreates them natively. The pinned GR00T source tree retains its
filesystem name, but its editable environment also embeds the old patch/source
identity. Archive that complete stopped tree before asking the installer to
recreate it:

```bash
test ! -e "$UPGRADE_BACKUP/Isaac-GR00T.pre-rename"
if [ -e "$HOME/groot_shadow/Isaac-GR00T" ]; then
  mv -- "$HOME/groot_shadow/Isaac-GR00T" \
    "$UPGRADE_BACKUP/Isaac-GR00T.pre-rename"
fi
```

If an operator chose a new checkout path that was not clean, move each
repository-owned `.venv` into the restricted backup before installation; do
not delete or overwrite it. Leave system Python and unrelated environments
alone.

On Thor:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/install-brain-host-prereqs.sh
ops/prepare-groot-runtime.sh --install
ops/bootstrap-brain.sh --check
ops/bootstrap-brain.sh --install
ops/install-groot-thor-shared-profiles.sh
```

`bootstrap-brain.sh --install` recreates the repository-owned environments
and rerenders the user units with the new checkout path, but preserves existing
`~/.config/ic-spine/*.env` values. That is why the environment audit in the
previous step is mandatory. Recreate the conformance-kit environment
separately as shown in [`REPRODUCIBLE-DEMO.md`](REPRODUCIBLE-DEMO.md).

Seed the new OpenClaw configuration, verify it exists, stop the temporary
Gateway/Seam owners, reapply reviewed provider settings, and synchronize the
playbook:

```bash
systemctl --user start ic-openclaw.service
test -s "$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json"
systemctl --user stop ic-openclaw.service ic-seam.service
ops/sync-playbook.sh
```

Compare the seeded file with `$UPGRADE_BACKUP/openclaw.json.pre-rename`. Keep
the new MCP command, agent policy, and renamed display values. Reapply only the
provider/model values needed by this deployment, then run the OpenClaw config
validation documented in the reproduction guide while the Gateway is stopped.

On the simulation host, reinstall the bridge from the new checkout rather than
moving the generated legacy helper. Use the same reviewed SSH target and the
new absolute model path:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/install-groot-two-host-bridge.sh \
  --thor-ssh YOUR_THOR_USER@YOUR_THOR_IP \
  --remote-checkpoint \
    /home/YOUR_THOR_USER/policy-gated-factory-robot-orchestrator-reference-models/order744-cont24 \
  --remote-state-root /home/YOUR_THOR_USER/.local/share/ic-spine/groot
```

The bridge installer refuses a differing existing configuration or generated
state. The preceding archive step makes their absence explicit while retaining
them for audit and rollback. If the installer still refuses, compare the named
item with the backup and stop; do not delete a file merely to bypass a refusal.

## 6. Validate both migration paths

A release is not upgrade-safe until both of these independent gates pass on
the exact published commit:

1. **Clean installation:** start from clean supported RTX and Thor hosts (or
   clean host state), follow [`REPRODUCIBLE-DEMO.md`](REPRODUCIBLE-DEMO.md),
   run all preflights and conformance checks, reset the scene, and complete the
   deterministic serial physical acceptance workflow.
2. **Upgrade installation:** start from the accepted pre-rename deployment,
   perform this stopped-service migration, then run the same health,
   conformance, reset, serial mission, journal, VLM, ROS-payload, and current
   Isaac-log checks.

Each gate must exercise the two Isaac surfaces separately. First follow the
[standalone workstation runbook](../ops/ISAAC-SIM-WORKSTATION.md) through its
stable 6.0.1 headless launch and scene-destructive
`accept-isaac-sim-workstation.sh` gate. Preserve the NVIDIA checker and
acceptance markers, then explicitly inspect, stop, and remove that confirmed
container before starting the independently pinned dev2/X11 GR00T path in the
[two-host guide](REPRODUCIBLE-DEMO.md). The standalone pass is not Thor or
GR00T evidence, and the historical two-host pass is not stable-baseline
evidence.

Before either start, inspect installed files for stale source paths:

```bash
rg -n 'industrial_claw|industrial-claw' \
  "$HOME/.config/ic-spine" "$HOME/.config/systemd/user" \
  "$HOME/.local/lib/policy-gated-factory-robot-orchestrator-reference" || true
systemctl --user daemon-reload
systemctl --user cat ic-seam.service ic-openclaw.service ic-chat.service
```

The Isaac launcher also refuses to reuse a stopped container. Before removing
the exact old container, capture its inspect record and current logs in the
restricted backup. Remove only that confirmed stopped container, then launch
the freshly prepared cell; never select a container solely by image or port.

Only the two published Hugging Face IDs may retain the old slug. Then run the
read-only and live checks in the reproduction guide, including
`ops/thor-deploy.sh --check`, both conformance commands, fresh Fast DDS
payloads, model/checkpoint verification, bridge-derived readiness, an explicit
scene reset, and the serial `full-groot-dual-tote` workflow. Confirm the exact
mission in authoritative state, journal, VLM evidence, and current-container
logs; a service catalog or model-list response alone is not acceptance.

Also verify the intentional CLI break in a newly created IC Spine environment:

```bash
ic-spine/.venv/bin/policy_gated_factory_robot_orchestrator_reference --help
test ! -e ic-spine/.venv/bin/industrial_claw
ic-spine/.venv/bin/python -c \
  'import policy_gated_factory_robot_orchestrator_reference'
```

Do not change the deployment manifest's historical `validated_on` date or
describe the earlier live run as post-rename validation. Record a new evidence
date and immutable commit only after the corresponding clean and upgrade gates
actually pass.

## Rollback

If validation fails, leave the cell idle, stop the new services and bridge,
and preserve their logs and state for diagnosis. Restore the old checkout,
operator environment files, installed units, secrets, and persistent paths
from the verified backup, rerender the old units from the old revision, and
restart only the previously enabled owners. Do not run old and new services
against the same writable state tree. Keep both backups until a complete
post-rollback health and scene-state check succeeds.
