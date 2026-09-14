# Upgrade after the product and project-prefix rename

This guide covers an existing installation that used the former
`Industrial Claw` product name, the `IC` project prefix, or both. The current
name is **Policy-Gated Factory Robot Orchestrator Reference**, abbreviated
**PGFR** in project-owned interfaces.

Schedule a maintenance window for this upgrade. There are no runtime
compatibility aliases: `IC_*` becomes `PGFR_*`, `ic-*` becomes
`pgfr-*`, `ic_*` becomes `pgfr_*`, and `/ic/*` becomes `/pgfr/*`. The change
also covers package names, command-line tools, HTTP headers, OpenClaw IDs,
readiness markers, schema IDs, persistent paths, and generated configuration.
Stop the project services and Isaac Sim on both hosts before changing paths
or installed files. Never run legacy and PGFR services against the same ports
or writable state.

The public installation now takes a user-trained local checkpoint. It does
not fetch a project checkpoint or recorded dataset. Preserve existing model
files and caches during migration; do not rewrite third-party snapshot metadata.
Export the selected local checkpoint using the [model guide](../reference/policy-gated-factory-robot-orchestrator-reference/groot/models/README.md)
and use its new metadata/identity consistently when regenerating profiles and
bridge contracts. An older mission result does not qualify a newly trained model.

## What changes

| Legacy name or default | New name or default | Action |
|---|---|---|
| `industrial_claw` Python distribution, import, and executable | `policy_gated_factory_robot_orchestrator_reference` | Recreate the PGFR Spine environment and update callers. There is no compatibility alias. |
| `ic-spine/`, `ic-console/`, `servers/ic-chat/`, `servers/ic-workflows/` | `pgfr-spine/`, `pgfr-console/`, `servers/pgfr-chat/`, `servers/pgfr-workflows/` | Recreate all four environments from their renamed lockfiles. |
| `ic_chat`, `ic_console`, `ic_workflows`, `ic_mcp`, `ic_conformance`, `ic_connector_sdk` | The equivalent `pgfr_*` imports | Update Python imports, editable sources, and entry points together. |
| `ic-chat`, `ic-console`, `ic-workflows`, `ic-mcp`, `ic-conformance`, `ic-connector-sdk` | The equivalent `pgfr-*` distribution and command names | Update scripts and automation; no compatibility executables are installed. |
| `IC_*` environment variables and `__IC_*__` template fields | `PGFR_*` and `__PGFR_*__` | Rename every project-owned key in copied configuration and secrets. NVIDIA, Hugging Face, ROS, and OpenClaw variables do not change. |
| `ic-*` user units, containers, readiness records, and log markers | `pgfr-*` names and `PGFR_*` markers | Stop and retire the old owners before installing or starting the new ones. |
| `X-IC-Chat`, `X-IC-Workflows` | `X-PGFR-Chat`, `X-PGFR-Workflows` | Update callers, CORS configuration, and service tokens atomically. |
| OpenClaw `ic-console`, `ic-floor`, and `ic-floor__*` IDs | `pgfr-console`, `pgfr-floor`, and `pgfr-floor__*` | Regenerate the OpenClaw configuration; do not copy the old generated file over it. |
| `/ic/*` ROS topics and `ic/...` schema IDs | `/pgfr/*` and `pgfr/...` | Rebuild the Isaac scripts mount and update both ROS hosts from the same revision. |
| `~/.config/ic-spine/` | `~/.config/pgfr-spine/` | Move the stopped configuration tree, then rename every project-owned environment key. |
| `~/.local/share/ic-spine/` | `~/.local/share/pgfr-spine/` | Move sessions, GPU history, GR00T state, and readiness records before rerunning installers. |
| `~/ic-journal/`, `~/ic_gpu_telemetry/`, `~/.ic_chat_sessions/` | The equivalent `pgfr` paths | Preserve mission evidence and history; do not merge old and new trees. |
| `reference/industrial-claw/` | `reference/policy-gated-factory-robot-orchestrator-reference/` | Use the new checkout; do not retain scripts that point into the old source tree. |
| `servers/industrial-claw-mcp/` | `servers/policy-gated-factory-robot-orchestrator-reference-mcp/` | Recreate the MCP virtual environment and update MCP client commands. Use the `pgfr-mcp` executable. |
| `skills/industrial-claw-orchestrator/` | `skills/policy-gated-factory-robot-orchestrator-reference-orchestrator/` | Re-run `ops/sync-playbook.sh` after installation. |
| `~/.industrial_claw/` | `~/.policy_gated_factory_robot_orchestrator_reference/` | Move CLI run and mock floor-state data if it must be retained. |
| `~/.industrial-claw/openclaw/` | `~/.policy-gated-factory-robot-orchestrator-reference/openclaw/` | Move the OpenClaw workspace while its services are stopped, then regenerate `openclaw.json` from the new template and reapply reviewed provider settings. |
| `~/industrial-claw-models/` | `~/policy-gated-factory-robot-orchestrator-reference-models/` | Move or restore the verified model tree and Hugging Face cache as one tree. |
| `~/.local/lib/industrial-claw/` | `~/.local/lib/policy-gated-factory-robot-orchestrator-reference/` | Reinstall the simulation-host bridge; do not copy the generated helper forward. |
| A checkout such as `~/industrial-claw/` | `~/Policy-Gated-Factory-Robot-Orchestrator-Reference/` | Use a clean checkout of the exact release commit. Rerender every path-bound unit. |

`~/.openclaw/secrets.env`, `~/groot_shadow/Isaac-GR00T/`, and official upstream
model caches keep their paths. Migrate project-owned paths according to the
table. Review the retained files: the secrets file can contain `IC_*` keys,
and generated OpenClaw configuration can contain old agent, MCP, or executable
identifiers. The `pgfr-*` units and `pgfr` state paths are new destinations, not
preserved aliases.

Do not rename an existing Isaac scripts mount while a container is using it.
Prepare a fresh mount with `ops/isaac-sim-workstation.sh --prepare` for
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
systemctl --user list-unit-files 'ic-*' 'pgfr-*'
systemctl --user list-units --all 'ic-*' 'pgfr-*'
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
```

If the legacy checkout has another path, substitute it in the two Git
commands. Save the output with the change record. Confirm that no mission,
reset, physical action, model request, or evidence write is in flight.

On Thor, explicitly stop every legacy owner that can use a path being migrated:

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

If the inventory shows units from an incomplete PGFR installation, stop those
exact `pgfr-*` units as well. Do not guess: record and stop only units owned by
this deployment.

Do not identify or terminate an arbitrary process only by port number. Verify
that all listed user units are inactive and that no container is using the
scripts mount before continuing.

## 2. Back up configuration and persistent data

Use an encrypted, access-controlled host snapshot when available. At minimum,
create a mode-0700 backup outside both the checkout and the directories being
migrated. Back up these items without printing their contents:

- `~/.config/ic-spine/` and `~/.config/systemd/user/ic-*`
- any `~/.config/pgfr-spine/` or `pgfr-*` unit files left by a partial attempt
- `~/.openclaw/secrets.env`
- `~/.industrial_claw/` and `~/.industrial-claw/`, when present
- `~/.local/share/ic-spine/`, `~/ic-journal/`, and any partial PGFR state
- `~/industrial-claw-models/`
- the legacy simulation-host bridge helper/configuration and external
  Isaac/GR00T state
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

After the backup is verified, disable the legacy units that were enabled in the
inventory. This prevents a reboot from starting old owners on the PGFR ports:

```bash
systemctl --user disable \
  ic-console.service ic-chat.service ic-workflows.service \
  ic-openclaw.service ic-seam.service ic-gpu-exporter.service \
  ic-perception-vlm.service ic-groot-shared-stack.target \
  ic-groot-two-host-bridge.service
systemctl --user daemon-reload
```

Keep the stopped unit files in the backup until rollback is no longer needed.
If a listed unit was never installed on that host, omit it rather than masking
the error.

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

Migrate the abbreviated project state separately. Run only a block whose source
exists, and stop if its destination already exists:

```bash
if [ -e "$HOME/.config/ic-spine" ]; then
  test ! -e "$HOME/.config/pgfr-spine"
  mv -- "$HOME/.config/ic-spine" "$HOME/.config/pgfr-spine"
fi
if [ -e "$HOME/.local/share/ic-spine" ]; then
  test ! -e "$HOME/.local/share/pgfr-spine"
  mv -- "$HOME/.local/share/ic-spine" "$HOME/.local/share/pgfr-spine"
fi
if [ -e "$HOME/ic-journal" ]; then
  test ! -e "$HOME/pgfr-journal"
  mv -- "$HOME/ic-journal" "$HOME/pgfr-journal"
fi
if [ -e "$HOME/ic_gpu_telemetry" ]; then
  test ! -e "$HOME/pgfr_gpu_telemetry"
  mv -- "$HOME/ic_gpu_telemetry" "$HOME/pgfr_gpu_telemetry"
fi
if [ -e "$HOME/.ic_chat_sessions" ]; then
  test ! -e "$HOME/.pgfr_chat_sessions"
  mv -- "$HOME/.ic_chat_sessions" "$HOME/.pgfr_chat_sessions"
fi
```

Do not rename installed `ic-*` unit files into place. Keep them stopped for
rollback; the installer renders fresh `pgfr-*` units from the candidate source.

If a destination already exists, stop and compare it against the backup; do
not overwrite or combine it. Verify the model tree after moving it:

```bash
ops/verify-groot-models.sh \
  "$HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
```

The bootstrap seeds missing environment files but preserves existing operator
configuration. After moving the configuration tree, rename every project-owned
`IC_*` key to the equivalent `PGFR_*` key. Do the same for project keys in
`~/.openclaw/secrets.env`; leave `NVIDIA_API_KEY`, `HF_*`, `OPENCLAW_*`,
`ROS_*`, and `RMW_*` keys unchanged. List files that still require review
without printing their values:

```bash
rg -l '^IC_[A-Z0-9_]*=' \
  "$HOME/.config/pgfr-spine" "$HOME/.openclaw/secrets.env" || true
rg -l 'Industrial Claw|industrial_claw|industrial-claw|ic-spine|ic-console|ic-chat|ic-workflows' \
  "$HOME/.config/pgfr-spine" "$HOME/.config/systemd/user" || true
```

Update old checkout, import/executable, model, source, patch, OpenClaw, and
bridge-helper paths. PGFR Chat and OpenClaw must use the same configuration
and state paths:

```dotenv
PGFR_OPENCLAW_CONFIG=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json
OPENCLAW_STATE_DIR=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw
OPENCLAW_CONFIG_PATH=/home/YOUR_USER/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json
```

Preserve third-party variables and upstream artifact identities. Review each
remaining project-owned legacy value; do not run an unrestricted
repository-wide substitution.

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
from the migrated `~/.local/share/pgfr-spine/groot/` tree into the backup. On
the simulation host, move the same two files from
`~/.local/share/pgfr-spine/groot/remote-thor-v36/`, plus the migrated
`~/.config/pgfr-spine/groot-two-host-bridge.env`. If present, also archive
`~/.config/pgfr-spine/groot-bridge-checkpoint/`, which is the prior installed
identity snapshot. Archive any generated bridge
helper found under either full-form path in the migration table; the new
installer recreates it from the candidate source. Keep mission journals, Chat
sessions, and evidence in place; they are persistent records, not readiness
signals.

Operator-authored `skills/wf-*` directories in the old checkout are deployment
data. Copy them into the candidate one at a time only after checking for a name
collision and reviewing the manifest. Rename their ownership marker from
`.ic-workflows-owned` to `.pgfr-workflows-owned`; PGFR Workflows deliberately
refuses to publish over a directory without the current marker. Do not copy or
merge the complete old `skills/` tree.

The playbook synchronizer migrates either the legacy or current marked block to
one current `PGFR-PLAYBOOK` block. Keep its timestamped backup until the new
OpenClaw configuration and tool list pass validation.

The shared profiles are generated from checkpoint identity. Archive them on
Thor while the stack is stopped; merely renaming environment keys cannot
update their fingerprint. Retain them for comparison with the newly generated
profiles, rather than copying them back:

```bash
: "${UPGRADE_BACKUP:?set the restricted upgrade backup directory first}"
for profile in shared-left shared-right; do
  profile_path="$HOME/.config/pgfr-spine/groot/$profile.env"
  if [ -e "$profile_path" ]; then
    test ! -e "$UPGRADE_BACKUP/$profile.env.before-checkpoint-export"
    mv -- "$profile_path" "$UPGRADE_BACKUP/$profile.env.before-checkpoint-export"
  fi
done
```

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
ops/install-groot-thor-shared-profiles.sh \
  --checkpoint-path "$HOME/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint"
```

`bootstrap-brain.sh --install` recreates the repository-owned environments
and rerenders the user units with the new checkout path, but preserves existing
`~/.config/pgfr-spine/*.env` values. That is why the environment audit in the
previous step is mandatory. Recreate the conformance-kit environment using
[the validation guide](VALIDATION.md#run-conformance-checks).

Seed the new OpenClaw configuration, verify it exists, stop the temporary
Gateway/Seam owners, reapply reviewed provider settings, and synchronize the
playbook:

```bash
systemctl --user start pgfr-openclaw.service
test -s "$HOME/.policy-gated-factory-robot-orchestrator-reference/openclaw/openclaw.json"
systemctl --user stop pgfr-openclaw.service pgfr-seam.service
ops/sync-playbook.sh
```

Compare the seeded file with `$UPGRADE_BACKUP/openclaw.json.pre-rename`. Keep
the new MCP command, agent policy, and renamed display values. Reapply only the
provider/model values needed by this deployment, then run the OpenClaw config
validation documented in the reproduction guide while the Gateway is stopped.

On the simulation host, reinstall the bridge from the new checkout rather than
moving the generated legacy helper. Use the same reviewed SSH target and the
new absolute model path. Copy the exported `pgfr_checkpoint.json` and its
sibling `SHA256SUMS` to the simulation host as described in the two-host guide:

```bash
cd "$HOME/Policy-Gated-Factory-Robot-Orchestrator-Reference"
ops/install-groot-two-host-bridge.sh \
  --thor-ssh YOUR_THOR_USER@YOUR_THOR_IP \
  --remote-checkpoint \
    /home/YOUR_THOR_USER/policy-gated-factory-robot-orchestrator-reference-models/my-checkpoint \
  --checkpoint-metadata /absolute/local/path/to/pgfr_checkpoint.json \
  --remote-state-root /home/YOUR_THOR_USER/.local/share/pgfr-spine/groot
```

The bridge installer refuses a differing existing configuration or generated
state. The preceding archive step makes their absence explicit while retaining
them for audit and rollback. If the installer still refuses, compare the named
item with the backup and stop; do not delete a file merely to bypass a refusal.

## 6. Validate both migration paths

Before claiming upgrade support, validate both paths against the same
published commit:

1. **Clean installation:** start from clean supported RTX and Thor hosts (or
   clean host state), follow [`REPRODUCIBLE-DEMO.md`](REPRODUCIBLE-DEMO.md),
   run all preflights and conformance checks, reset the scene, and complete the
   deterministic serial physical acceptance workflow.
2. **Upgrade installation:** start from the accepted pre-rename deployment,
   perform this stopped-service migration, then run the same health,
   conformance, reset, serial mission, journal, VLM, ROS-payload, and current
   Isaac-log checks.

Each gate must exercise both simulator profiles separately. First follow the
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
  "$HOME/.config/pgfr-spine" "$HOME/.config/systemd/user" \
  "$HOME/.local/lib/policy-gated-factory-robot-orchestrator-reference" || true
systemctl --user daemon-reload
systemctl --user cat pgfr-seam.service pgfr-openclaw.service pgfr-chat.service
```

The Isaac launcher also refuses to reuse a stopped container. Before removing
the exact old container, capture its inspect record and current logs in the
restricted backup. Remove only that confirmed stopped container, then launch
the freshly prepared cell; never select a container solely by image or port.

Preserve historical model metadata. Run the deployment readiness checks and
[mission acceptance checks](VALIDATION.md), including
`ops/thor-deploy.sh --check`, both conformance commands, fresh Fast DDS
payloads, model/checkpoint verification, bridge-derived readiness, an explicit
scene reset, and the serial `full-groot-dual-tote` workflow. Confirm the exact
mission in authoritative state, journal, VLM evidence, and current-container
logs; a service catalog or model-list response alone is not acceptance.

Also verify the intentional CLI break in a newly created PGFR Spine environment:

```bash
pgfr-spine/.venv/bin/policy_gated_factory_robot_orchestrator_reference --help
test ! -e pgfr-spine/.venv/bin/industrial_claw
pgfr-spine/.venv/bin/python -c \
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
