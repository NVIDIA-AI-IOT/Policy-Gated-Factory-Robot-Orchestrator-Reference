# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run bounded stock-Lula FK jobs prepared after the dual-arm capture.

This is executed inside the already-running Isaac process through cmd.py.  It
accepts only request/output paths under the mounted capture tree and delegates
every job to the previously certified single-dataset stock-Lula converter.
"""

import json
import os
import traceback


try:
    if S.get("task") is not None:
        raise RuntimeError("refusing FK batch while a robot task is active")

    _jobs_path = globals().get(
        "_PGFR_NATIVE_DROID_FK_JOBS_PATH",
        "/scripts/native_droid_work/dual_arm_fk_jobs.json",
    )
    _done_path = globals().get(
        "_PGFR_NATIVE_DROID_FK_DONE_PATH",
        "/scripts/native_droid_work/dual_arm_fk_jobs.done.json",
    )
    _expected_jobs = int(globals().get("_PGFR_NATIVE_DROID_FK_EXPECTED_JOBS", 6))
    with open(_jobs_path, encoding="utf-8") as _stream:
        _jobs_payload = json.load(_stream)
    _jobs = _jobs_payload.get("jobs", [])
    if (
        _jobs_payload.get("schema_version") != 1
        or len(_jobs) != _expected_jobs
    ):
        raise ValueError(
            "dual-arm FK manifest must contain exactly %d jobs" % _expected_jobs
        )

    _root = "/scripts/capture_batches/"
    _reports = []
    for _index, _job in enumerate(_jobs):
        _request = os.path.realpath(str(_job["request"]))
        _output = os.path.realpath(str(_job["output"]))
        if not _request.startswith(_root) or not _output.startswith(_root):
            raise ValueError("FK job escaped the capture tree")
        if not os.path.isfile(_request):
            raise FileNotFoundError(_request)

        if os.path.isfile(_output):
            with open(_output, encoding="utf-8") as _stream:
                _existing = json.load(_stream)
            if (
                _existing.get("frame") != "panda_link8"
                or len(_existing.get("episodes", []))
                != int(_job["expected_episodes"])
            ):
                raise ValueError("existing FK output does not match its job: " + _output)
            _status = "reused"
        else:
            globals()["_PGFR_NATIVE_DROID_FK_REQUEST"] = _request
            globals()["_PGFR_NATIVE_DROID_FK_OUTPUT"] = _output
            _worker = "/scripts/native_droid_work/compute_native_droid_fk_in_isaac.py"
            with open(_worker, encoding="utf-8") as _stream:
                exec(compile(_stream.read(), _worker, "exec"), globals())
            if not os.path.isfile(_output):
                raise RuntimeError("FK worker did not create output: " + _output)
            with open(_output, encoding="utf-8") as _stream:
                _result = json.load(_stream)
            if (
                _result.get("frame") != "panda_link8"
                or len(_result.get("episodes", []))
                != int(_job["expected_episodes"])
            ):
                raise RuntimeError("new FK output failed validation: " + _output)
            _status = "computed"

        _reports.append(
            {
                "index": _index,
                "arm": _job["arm"],
                "color": _job["color"],
                "request": _request,
                "output": _output,
                "episodes": int(_job["expected_episodes"]),
                "status": _status,
            }
        )
        print(
            "PGFR_DUAL_ARM_FK_JOB_DONE index=%d arm=%s color=%s status=%s"
            % (_index, _job["arm"], _job["color"], _status),
            flush=True,
        )

    with open(_done_path, "w", encoding="utf-8") as _stream:
        json.dump({"schema_version": 1, "jobs": _reports}, _stream, indent=2)
        _stream.write("\n")
    print("PGFR_DUAL_ARM_FK_BATCH_DONE jobs=%d" % _expected_jobs, flush=True)
except Exception:
    print("PGFR_DUAL_ARM_FK_BATCH_ERROR:\n" + traceback.format_exc(), flush=True)
