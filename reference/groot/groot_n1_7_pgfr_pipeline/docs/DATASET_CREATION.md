# Create your own demonstration dataset

Use this workflow to collect your own demonstrations. The repository supplies
capture/conversion tools and small calibration records, but no training corpus.
Validate the expert profile in Isaac Sim on your workstation before collecting
data; offline tests cannot validate grasp physics or camera timing.

## Adapt to your own Isaac Sim scene

The bundled Franka factory scene and native DROID schema are a reference
example. You may use your own Isaac Sim scene, robot, and demonstration dataset,
then fine-tune GR00T for that task. The commands below target the bundled
example; other scenes and datasets require compatible adapters.

Adapt these parts together:

- **Capture and conversion:** scene paths, robot/controller interfaces, task
  labels, and synchronized images, measured states, and applied action labels.
- **State and action mapping:** joint order, units, coordinate frames, forward
  kinematics, gripper semantics, and absolute versus relative actions.
- **Cameras and training:** camera views/calibration, timestamps, image shape,
  history and action horizon, dataset checks, and the modality/embodiment
  configuration appropriate to your robot and base checkpoint.
- **Runtime and validation:** inference observations, action execution, scene
  queries, policy limits, and task-specific success verification.

Recompute statistics for your adapted training data and
[validate the resulting policy](VALIDATION.md) in your custom scene before
deployment. The supplied launcher and runtime enforce the example's
contracts and must be adapted when those contracts change.

## Prerequisites and paths

Use the pinned Isaac Sim development image and external NVIDIA scene assets
specified by the [two-host guide](../../../../docs/REPRODUCIBLE-DEMO.md).
Have a CUDA capable GPU, NVIDIA Container Toolkit, Docker, a ROS 2 Jazzy
environment, and a reviewed CPU FFmpeg build selected using the
[training environment recipe](FINETUNING_RECIPE.md#select-and-check-the-local-cpu-encoder).
The recorder Python needs `rclpy`, `sensor_msgs`, `std_msgs`, NumPy,
Pillow, and this repository's `pgfr-spine` package. Conversion needs NumPy,
pandas, pyarrow, and SciPy; the prepared GR00T training environment supplies
these. Recorder Python and GR00T training Python are separate environments.

Read the [NVIDIA Isaac Sim Additional Software and Materials License](https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/)
and the applicable asset terms before pulling or running the official runtime.
The project source license does not grant rights to all Kit/runtime components
or scene assets; preserve the runtime
[licenses and notices](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html).
If you accept those terms, explicitly set this operator input in the shell
used for the capture and FK commands:

```bash
# Set only after reading and accepting the applicable NVIDIA terms.
export ACCEPT_EULA=Y
```

The commands below pass that explicit choice to the official pinned image.
They mount project source directly and do not build or publish a derived
image. Preparing capture scripts does not accept terms or start a runtime.

Set absolute paths for your checkout and new outputs:

```bash
export REPO=/absolute/path/Policy-Gated-Factory-Robot-Orchestrator-Reference
export PIPELINE="$REPO/reference/groot/groot_n1_7_pgfr_pipeline"
export DATA_ROOT="$HOME/pgfr-user-data"
export CAPTURE_MOUNT="$DATA_ROOT/isaac-capture-scripts"
mkdir -p "$DATA_ROOT"
python3 "$PIPELINE/pipeline/capture/prepare_capture.py" --mount "$CAPTURE_MOUNT"
```

The staging command refuses an existing mount and starts nothing. It copies the
public scene and stock physical RMPflow expert, shape layout, and passive
synchronization observer. No GR00T checkpoint, relay, or Thor service is required.

## Launch an isolated expert simulator

Run this in a separate maintenance session with capacity for the simulator.
Use a new container name, new scripts mount, and an unused nonzero ROS domain
(the example uses 83). Check that domain is not used by your live robots or
services. Do not point the recorder at a serving/production domain. This is
an explicit data-collection run: the recorder will stage objects and move arms.

```bash
export CAPTURE_DOMAIN=83
export ISAAC_CAPTURE_IMAGE='nvcr.io/nvidia/isaac-sim:6.0.0-dev2@sha256:c3e7bef5b2bfdb9972807c34195206078372bf8c6cff79716be130a3fe3e9ce9'
docker pull "$ISAAC_CAPTURE_IMAGE"
docker run -d --pull never --name pgfr-data-capture --gpus all --network host \
  --entrypoint /isaac-sim/isaac-sim.sh \
  -e ACCEPT_EULA="${ACCEPT_EULA:?Read and accept NVIDIA terms before launch}" \
  -e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1 \
  -e ROS_DOMAIN_ID="$CAPTURE_DOMAIN" -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  -e PGFR_SCENE_PROFILE=expert_capture -e PGFR_CAPTURE_ONLY=1 \
  -e PGFR_CAMERA_PROFILE=capture -e PGFR_GROOT_READY_ARM=both \
  -e PGFR_GROOT_READY_LAYOUT=3 \
  -v "$CAPTURE_MOUNT:/scripts:ro" \
  "$ISAAC_CAPTURE_IMAGE" --no-window --exec /scripts/startup.py

docker logs pgfr-data-capture
```

Proceed only after `PGFR_EXPERT_CAPTURE_READY`, `PGFR_SYNC_CAPTURE_READY`, and
`STARTUP_DONE` appear without startup/physics errors. The profile is fixed at
startup; a reset command cannot turn a learned-policy scene into an expert
scene or switch the expert scene into a learned-policy scene. The observer
records applied RMPflow joint/finger commands; it never synthesizes action
labels from the next measured state.

In a ROS 2 Jazzy shell, create the recorder environment and verify importability:

```bash
source /opt/ros/jazzy/setup.bash
python3 -m venv --system-site-packages "$DATA_ROOT/recorder-env"
"$DATA_ROOT/recorder-env/bin/pip" install "$REPO/pgfr-spine" 'numpy==1.26.4' Pillow
export RECORDER_PYTHON="$DATA_ROOT/recorder-env/bin/python"
export ROS_DOMAIN_ID="$CAPTURE_DOMAIN"
export PGFR_CAPTURE_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
"$RECORDER_PYTHON" -c 'import rclpy, numpy, PIL; from sensor_msgs.msg import Image'
ros2 topic list
```

Confirm `/pgfr/floor_state`, `/pgfr/sync_sample`, and left/right wrist/outside
camera topics exist. Read floor state to confirm the expert simulator is idle.
Do not run a mission sender or chat orchestrator in this domain during capture.

## Capture staged sequences

This example collects one cohort for one arm; repeat with new directories,
seeds, layouts, and orders to cover both arms and each deployment context:

```bash
"$RECORDER_PYTHON" "$PIPELINE/pipeline/capture/record_pgfr_green_red_blue_staged_synced.py" \
  --output "$DATA_ROOT/raw/left-layout3-green-red-blue" \
  --arm franka_left --layout 3 --seed-start 5000 \
  --order green red blue --record-first --sequences 24 --max-attempts 72
```

Use `--arm franka_right` and a different output directory for the other arm.
`--order` must be a permutation of all three colors. Without `--record-first`,
the first move establishes accumulated-scene context and only stages two and
three are saved. With it, all three stages are saved. A sequence is accepted
only if every recorded stage passes. Twenty-four requested sequences are an
example collection size, not evidence that this amount is sufficient to train.

The recorder stages a red cube, blue cylinder, and green brick, then commands
one arm serially. It checks 60 Hz physics telemetry, 30 Hz camera production,
15 Hz retention, paired camera timestamps, exact applied command provenance,
finite state/action values, minimum duration, distractor displacement, grasp,
release, and final placement. It writes per-attempt quality records and an
accepted manifest. A command is published once after DDS discovery; an unknown
completion aborts collection, so inspect the simulator before another run.

Each accepted `raw/COHORT/COLOR/ep_NNN/` contains `states.json`, `task.txt`,
`scene.json`, `capture_quality.json`, and timestamp-matched `wrist/` and
`outside/` JPEG sequences. State and action are seven Panda joints plus one
finger width in meters. The recorded instruction names the object and target
pad, for example `pick the green brick and place it on the green pad`. Read
`task.txt` for each episode's instruction.

Keep training, validation, and test cohorts separate by complete sequence and
seed/layout; never split adjacent frames from one sequence across partitions.
Retain failures/attempt records for auditing, but do not include rejected
candidates in training. Record scene/controller revision, camera calibration,
seeds, arm, layout, order, and any exclusions. Distribution across colors,
arms, layouts, empty/occupied tote contexts, and deployment order must be
chosen and evaluated by the dataset creator.

## Convert accepted episodes and compute stock FK

Prepare the training environment from [the recipe](FINETUNING_RECIPE.md), then
set `GROOT_PYTHON` to its interpreter. Convert one accepted color/cohort at a
time. Keep each resulting native dataset as a separate training input; do not
combine folders by overwriting episode numbers.

Set `PGFR_FFMPEG_BIN` to the reviewed executable from that recipe. Each
conversion rechecks its reported build/license and runs a tiny CPU
scale/libx264/MP4 encode through pipes before creating the destination.

```bash
export COHORT=left-layout3-green-red-blue
export COLOR=green
export JOINT_DATA="$DATA_ROOT/joint/$COHORT-$COLOR"
export NATIVE_DATA="$DATA_ROOT/native/$COHORT-$COLOR"
mkdir -p "$DATA_ROOT/fk"
"$GROOT_PYTHON" "$PIPELINE/pipeline/conversion/convert_pgfr_to_lerobot.py" \
  --src-root "$DATA_ROOT/raw/$COHORT/$COLOR" --dst "$JOINT_DATA" --fps 15 \
  --ffmpeg "${PGFR_FFMPEG_BIN:?Select and check the local CPU FFmpeg first}" \
  --require-command-actions --required-action-source observed_exact_applied_joint_target \
  --strict-frame-sequences
"$GROOT_PYTHON" "$PIPELINE/pipeline/conversion/build_native_droid_dataset.py" export \
  --source "$JOINT_DATA" --request "$DATA_ROOT/fk/$COHORT-$COLOR-request.json"
```

Converters refuse an existing output. Use a fresh destination after correcting
bad inputs. Do not silently trim terminal frames: if an explicit trim is
justified, preserve raw capture, record the reason, and re-evaluate duration
and action-horizon coverage.

Keep `meta/ffmpeg_provenance.json`: it records the selected executable, its
SHA-256, reported configuration/license, and successful CPU encoding probe.
The native builder copies this file alongside the resulting training videos.
This report does not inventory linked libraries or certify distribution rights.

Compute FK in a **separate headless Isaac process**, with no scene or ROS
connections. This uses the image's stock Franka Lula robot description and
`panda_link8` frame, not an approximate handwritten kinematics model:

```bash
docker run --rm --pull never --name pgfr-data-fk --gpus all --network none \
  --entrypoint /isaac-sim/python.sh \
  -e ACCEPT_EULA="${ACCEPT_EULA:?Read and accept NVIDIA terms before launch}" \
  -e OMNI_TELEMETRY_DISABLE_ANONYMOUS_DATA=1 \
  -v "$PIPELINE:/pipeline:ro" -v "$DATA_ROOT:/data" \
  "$ISAAC_CAPTURE_IMAGE" \
  /pipeline/pipeline/conversion/compute_native_droid_fk_in_isaac.py \
  --request "/data/fk/$COHORT-$COLOR-request.json" \
  --output "/data/fk/$COHORT-$COLOR-lula.json"
"$GROOT_PYTHON" "$PIPELINE/pipeline/conversion/build_native_droid_dataset.py" build \
  --source "$JOINT_DATA" --fk-results "$DATA_ROOT/fk/$COHORT-$COLOR-lula.json" \
  --output "$NATIVE_DATA"
```

FK results carry the SHA-256 of each source parquet. The native builder rejects
stale or mismatched FK, non-finite arrays, and invalid rotation matrices. The
native state/action order is EEF pose `[xyz, rotation6D]` (9), normalized gripper
(1; 0 open, 1 closed), and seven joints: 17 values total. States and actions
are stored as absolute values. GR00T's modality config converts EEF/joint actions
to relative action chunks of length 40 during loading; gripper remains absolute.
Videos are 320×180, exterior followed by wrist, with current-frame history `[0]`.

## Check decoding in the actual training environment

The converter invokes an FFmpeg executable; TorchCodec loads native FFmpeg
shared libraries inside Python. `--ffmpeg` and `PGFR_FFMPEG_BIN` do not select
those libraries. Run this on a real converted video with the same interpreter
and native-library environment you will use for statistics and training:

```bash
export TRAIN_VIDEO="$NATIVE_DATA/videos/chunk-000/observation.images.exterior_1_left/episode_000000.mp4"
"$GROOT_PYTHON" - "$TRAIN_VIDEO" <<'CHECK_VIDEO'
import sys
from torchcodec.decoders import VideoDecoder
decoder = VideoDecoder(sys.argv[1], device="cpu")
frame = decoder.get_frame_at(0).data
assert tuple(frame.shape) == (3, 180, 320), tuple(frame.shape)
print("Decoded training frame:", tuple(frame.shape), frame.dtype)
CHECK_VIDEO
```

A missing `libav*` library, unsupported FFmpeg ABI, or decode error must be
resolved in this local training environment before computing statistics or
training. Installing a different FFmpeg executable alone does not establish
that TorchCodec can load its required shared-library ABI. Retain package/source
provenance for those libraries too. The one-frame check establishes basic
decodability; it does not validate every frame, camera synchronization, or
physical demonstration quality.

## Generate real statistics before training

The native builder intentionally does **not** create empty statistics files.
Compute absolute and relative statistics using the exact training modality:

```bash
cd "$ISAAC_GROOT_ROOT"
"$GROOT_PYTHON" gr00t/data/stats.py \
  --dataset-path "$NATIVE_DATA" \
  --embodiment-tag OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT \
  --modality-config-path "$PIPELINE/pipeline/training/droid_checkpoint_single_frame_config.py"
```

Repeat for every training dataset. Expect populated `meta/stats.json` for
17D state/action and `meta/relative_stats.json` for 40×9 EEF and 40×7 joint
chunks. Statistics must come from training episodes only. Rebuild into a fresh
native output after data changes rather than trusting statistics cached against
older data; upstream cache fingerprints describe feature/config contracts.
The training launcher checks statistics, video/file presence, episode counts,
frame totals, and the native layout before it invokes GR00T.

## Dataset rights and provenance

The repository's source license does not automatically license NVIDIA assets,
base weights, or datasets you create. Record the licenses/terms for scene and
robot assets, the origin of demonstrations, consent/rights for any externally
recorded imagery, and your chosen dataset distribution terms. Retain NVIDIA
and upstream attribution. Do not label generated data CC BY 4.0 merely because
an earlier development collection used that label. Publish data or models only
after your applicable release review; no dataset is uploaded by these tools.
