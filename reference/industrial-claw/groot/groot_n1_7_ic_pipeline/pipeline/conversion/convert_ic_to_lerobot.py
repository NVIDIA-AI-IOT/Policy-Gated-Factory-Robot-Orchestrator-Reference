# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import argparse, os, json, subprocess, glob, numpy as np, pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--src-root", default=os.path.expanduser("~/ic_demos"))
parser.add_argument("--dst", default=os.path.expanduser("~/ic_demos/lerobot/ic_sort"))
parser.add_argument("--fps", type=int, default=12)
parser.add_argument(
    "--require-command-actions",
    action="store_true",
    help="Reject episodes without a recorded command at every frame.",
)
parser.add_argument(
    "--required-action-source",
    default="",
    help="When set, require every recorded command to declare this exact source.",
)
parser.add_argument(
    "--strict-frame-sequences",
    action="store_true",
    help="Require continuous state indices/timestamps and both camera files at every frame.",
)
parser.add_argument(
    "--trim-terminal-frames",
    type=int,
    default=0,
    help=(
        "Exclude this many terminal frames from every derived episode. "
        "The raw capture is never modified."
    ),
)
args = parser.parse_args()

if args.trim_terminal_frames < 0:
    parser.error("--trim-terminal-frames must be non-negative")

SRC_ROOT = os.path.abspath(os.path.expanduser(args.src_root))
DST      = os.path.abspath(os.path.expanduser(args.dst))
FPS      = args.fps
VW, VH   = 320, 180

eps = sorted(glob.glob(SRC_ROOT + "/ep_[0-9]*"))
assert eps, "no ep_NNN episodes under " + SRC_ROOT
assert os.path.realpath(DST) != os.path.realpath(SRC_ROOT), "destination must differ from source"

# clean slate
import shutil; shutil.rmtree(DST, ignore_errors=True)
os.makedirs(DST + "/data/chunk-000")
os.makedirs(DST + "/meta")
for vk in ("observation.images.wrist", "observation.images.front"):
    os.makedirs(DST + "/videos/chunk-000/" + vk)

def enc(srcdir, outmp4, frames):
    r = subprocess.run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", srcdir + "/%04d.jpg",
                        "-vf", "scale=%d:%d" % (VW, VH), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-frames:v", str(frames), "-r", str(FPS), outmp4], capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG ERR", outmp4, "\n", r.stderr[-400:], flush=True)
    return r.returncode == 0

tasks = []
def task_idx(t):
    if t not in tasks: tasks.append(t)
    return tasks.index(t)

all_S, all_A, episodes_meta = [], [], []
gindex = total_frames = 0

for ei, epdir in enumerate(eps):
    raw_states = json.load(open(epdir + "/states.json"))
    raw_N = len(raw_states)
    if args.trim_terminal_frames >= raw_N:
        raise ValueError(
            "terminal trim removes the complete episode: %s (%d frames, trim=%d)"
            % (epdir, raw_N, args.trim_terminal_frames)
        )
    states = (
        raw_states[: raw_N - args.trim_terminal_frames]
        if args.trim_terminal_frames
        else raw_states
    )
    N = len(states)
    if N <= 20:
        raise ValueError("episode is too short: %s (%d frames)" % (epdir, N))
    task = open(epdir + "/task.txt").read().strip()
    ti = task_idx(task)
    S = np.zeros((N, 8), dtype=np.float32)
    for i, s in enumerate(states):
        j = s["fl_joints"]
        if j is None or len(j) < 8 or not np.isfinite(j[:8]).all():
            raise ValueError("invalid joints in %s frame %d" % (epdir, i))
        S[i, :7] = j[:7]; S[i, 7] = j[7]   # 7 arm joints + gripper
    command_actions = [s.get("fl_action") for s in states]
    has_commands = [action is not None for action in command_actions]
    if any(has_commands) and not all(has_commands):
        raise ValueError("episode mixes commanded and inferred actions: %s" % epdir)
    if args.require_command_actions and not all(has_commands):
        raise ValueError("episode is missing required commanded actions: %s" % epdir)
    if all(has_commands):
        A = np.zeros_like(S)
        for i, action in enumerate(command_actions):
            if len(action) < 8 or not np.isfinite(action[:8]).all():
                raise ValueError("invalid commanded action in %s frame %d" % (epdir, i))
            A[i, :7] = action[:7]
            A[i, 7] = action[7]
        recorded_sources = {
            s.get("fl_action_source") for s in states if s.get("fl_action_source")
        }
        if len(recorded_sources) > 1:
            raise ValueError("episode mixes action sources: %s" % epdir)
        action_source = (
            next(iter(recorded_sources))
            if recorded_sources
            else "commanded_joint_target"
        )
        if args.required_action_source and action_source != args.required_action_source:
            raise ValueError(
                "unexpected action source in %s: %s != %s"
                % (epdir, action_source, args.required_action_source)
            )
    else:
        A = np.zeros_like(S)
        A[:-1] = S[1:]
        A[-1] = S[-1]
        action_source = "next_measured_state"
    ts = np.array([s["t"] for s in states], dtype=np.float32)
    if args.strict_frame_sequences:
        indices = np.asarray([s.get("i") for s in states])
        expected_indices = np.arange(N)
        if not np.array_equal(indices, expected_indices):
            raise ValueError("non-continuous state indices in %s" % epdir)
        expected_ts = expected_indices / float(FPS)
        if not np.allclose(ts, expected_ts, atol=1e-5, rtol=0.0):
            raise ValueError("non-continuous %d Hz timestamps in %s" % (FPS, epdir))
    all_S.append(S); all_A.append(A)
    for camera in ("wrist", "outside"):
        frame_paths = sorted(glob.glob(epdir + "/%s/[0-9][0-9][0-9][0-9].jpg" % camera))
        if args.strict_frame_sequences:
            # Validate the complete immutable raw sequence, including terminal
            # frames deliberately excluded from the derived dataset.
            expected_paths = [epdir + "/%s/%04d.jpg" % (camera, i) for i in range(raw_N)]
            if frame_paths != expected_paths:
                raise FileNotFoundError(
                    "non-continuous %s frame sequence in %s: expected %d, found %d"
                    % (camera, epdir, raw_N, len(frame_paths))
                )
        elif not os.path.isfile(epdir + "/%s/%04d.jpg" % (camera, N - 1)):
            raise FileNotFoundError("missing %s frame %d in %s" % (camera, N - 1, epdir))
    if not enc(epdir + "/wrist", DST + "/videos/chunk-000/observation.images.wrist/episode_%06d.mp4" % ei, N):
        raise RuntimeError("failed to encode wrist video for %s" % epdir)
    if not enc(epdir + "/outside", DST + "/videos/chunk-000/observation.images.front/episode_%06d.mp4" % ei, N):
        raise RuntimeError("failed to encode outside video for %s" % epdir)
    df = pd.DataFrame({
        "observation.state": [S[i] for i in range(N)],
        "action":            [A[i] for i in range(N)],
        "timestamp":     ts,
        "frame_index":   np.arange(N, dtype=np.int64),
        "episode_index": np.full(N, ei, dtype=np.int64),
        "index":         np.arange(gindex, gindex + N, dtype=np.int64),
        "task_index":    np.full(N, ti, dtype=np.int64),
    })
    df.to_parquet(DST + "/data/chunk-000/episode_%06d.parquet" % ei, index=False)
    episodes_meta.append(
        {
            "episode_index": ei,
            "tasks": [task],
            "length": N,
            "action_source": action_source,
            "terminal_frames_trimmed": args.trim_terminal_frames,
        }
    )
    gindex += N; total_frames += N
    print(
        "ep %02d N=%d raw_N=%d trim=%d task_idx=%d action_source=%s (%s)"
        % (ei, N, raw_N, args.trim_terminal_frames, ti, action_source, task),
        flush=True,
    )

SS = np.concatenate(all_S, 0); AA = np.concatenate(all_A, 0)
def stt(x):
    x = np.asarray(x, dtype=np.float64)
    return {"mean": x.mean(0).tolist(), "std": (x.std(0) + 1e-8).tolist(),
            "min": x.min(0).tolist(), "max": x.max(0).tolist(),
            "q01": np.quantile(x, 0.01, 0).tolist(), "q99": np.quantile(x, 0.99, 0).tolist()}
json.dump({"action": stt(AA), "observation.state": stt(SS)}, open(DST + "/meta/stats.json", "w"), indent=2)

json.dump({
    "state":  {"single_arm": {"start": 0, "end": 7}, "gripper": {"start": 7, "end": 8}},
    "action": {"single_arm": {"start": 0, "end": 7}, "gripper": {"start": 7, "end": 8}},
    "video":  {"front": {"original_key": "observation.images.front"},
               "wrist": {"original_key": "observation.images.wrist"}},
    "annotation": {"human.task_description": {"original_key": "task_index"}},
}, open(DST + "/meta/modality.json", "w"), indent=2)

json.dump({
    "codebase_version": "v2.1", "robot_type": "ic_franka",
    "total_episodes": len(eps), "total_frames": total_frames, "total_tasks": len(tasks),
    "total_videos": len(eps) * 2, "total_chunks": 1, "chunks_size": 1000, "fps": FPS,
    "data_path":  "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
    "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
    "splits": {"train": "0:%d" % len(eps)},
    "features": {
        "action":            {"dtype": "float32", "shape": [8]},
        "observation.state": {"dtype": "float32", "shape": [8]},
        "observation.images.wrist": {"dtype": "video", "shape": [VH, VW, 3]},
        "observation.images.front": {"dtype": "video", "shape": [VH, VW, 3]},
        "timestamp":     {"dtype": "float32", "shape": [1]},
        "frame_index":   {"dtype": "int64", "shape": [1]},
        "episode_index": {"dtype": "int64", "shape": [1]},
        "index":         {"dtype": "int64", "shape": [1]},
        "task_index":    {"dtype": "int64", "shape": [1]},
    },
}, open(DST + "/meta/info.json", "w"), indent=2)

with open(DST + "/meta/tasks.jsonl", "w") as f:
    for i, t in enumerate(tasks): f.write(json.dumps({"task_index": i, "task": t}) + "\n")
with open(DST + "/meta/episodes.jsonl", "w") as f:
    for e in episodes_meta: f.write(json.dumps(e) + "\n")

print("CONVERTED %d episodes, %d frames, %d tasks -> %s" % (len(eps), total_frames, len(tasks), DST), flush=True)
