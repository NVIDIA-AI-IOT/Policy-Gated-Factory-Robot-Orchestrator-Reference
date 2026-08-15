# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
# ic_cams_rp.py — hardened IC cameras on replicator render products (NO viewports).
#
# Replaces gr00t_cams.py + cmd_rebuild_verify_cams.py + cmd_fix_outside_cam.py in
# the bring-up. Render products created via rep.create.render_product render every
# frame regardless of GUI layout, so docking/tabbing viewport panels can never
# silently blind the policy or the verifier again (the 2026-07-16 failure class).
# Viewport panels remain purely cosmetic for humans.
#
# Production publishes the certified full camera set.  Set
# IC_CAMERA_PROFILE=capture at launch for the native-DROID capture profile:
# both left/right wrist+outside pairs at 320x180, rendered at 30 Hz and retained
# at the native DROID 15 fps dataset cadence.  Publishing both arm domains at
# startup lets a capture campaign switch arms without rebuilding camera graphs
# or restarting Isaac Sim.
#
# Publishes:
#   wrist_cam/*   <- /Workcell/Franka_Left/panda_hand/WristCam (baked 06-22 matrix)
#   outside_cam/* <- /RackCam_B at the CONTRACT pose (production_contract_expected.json)
#   inspect_cam/* <- same /RackCam_B render product, verify topic
#   inspect_vlm_cam/* <- /RackCam_B at 640x360 in capture mode (VLM-only)
#   rack_cam/*    <- /RackCam_A
#   table_cam/*   <- /Cam_Table at the operator-approved 2026-07-24 pose
import json
import os
import traceback

os.environ.setdefault("ROS_DOMAIN_ID", "0")
os.environ.setdefault("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")

def _ic_cams_rp_build():
    globals()["_IC_CAMS_RP_READY"] = False
    globals()["_IC_TABLE_CAM_CONTRACT"] = None
    globals()["_IC_CAMERA_TOPIC_CONTRACT"] = None
    globals()["_IC_VLM_CAMERA_TOPIC_CONTRACT"] = None
    try:
        import omni
        import omni.graph.core as og
        import omni.replicator.core as rep
        from isaacsim.core.utils import extensions
        from pxr import Gf, UsdGeom
    
        extensions.enable_extension("isaacsim.ros2.bridge")
        stage = omni.usd.get_context().get_stage()
        camera_profile = os.environ.get("IC_CAMERA_PROFILE", "production").strip().lower()
        if camera_profile not in ("production", "capture"):
            raise ValueError("IC_CAMERA_PROFILE must be production or capture")
    
        # instanced gripper geometry does not render in render products (verified 06-22)
        for arm in ["Franka_Left", "Franka_Right"]:
            for part in ["panda_hand/geometry", "panda_leftfinger/geometry", "panda_rightfinger/geometry"]:
                gp = stage.GetPrimAtPath("/Workcell/%s/%s" % (arm, part))
                if gp.IsValid():
                    gp.SetInstanceable(False)
    
        # wrist camera on the hand — baked eye-in-hand matrix (captured 06-22)
        HAND = "/Workcell/Franka_Left/panda_hand"
        WCAM = HAND + "/WristCam"
        if stage.GetPrimAtPath(WCAM).IsValid():
            stage.RemovePrim(WCAM)
        wc = UsdGeom.Camera.Define(stage, WCAM)
        wc.GetFocalLengthAttr().Set(16.0)
        wc.GetClippingRangeAttr().Set(Gf.Vec2f(0.005, 12.0))
        xf = UsdGeom.Xformable(wc.GetPrim())
        xf.ClearXformOpOrder()
        _M = Gf.Matrix4d(-0.659877, -0.127132, -0.740540, 0.0,
                         -0.214963,  0.976329,  0.023937, 0.0,
                          0.719968,  0.174984, -0.671585, 0.0,
                          0.270284,  0.045531, -0.041819, 1.0)
        xf.AddTransformOp().Set(_M)
    
        # outside camera = /RackCam_B at the recorded CONTRACT pose (no invented numbers)
        exp = json.load(open("/scripts/production_contract_expected.json"))
        cam = exp["cameras"]["outside"]
        q = cam["quaternion_opengl_xyzw"]
        rot = Gf.Quatd(float(q[3]), Gf.Vec3d(float(q[0]), float(q[1]), float(q[2])))
        M = Gf.Matrix4d().SetRotate(rot)
        M.SetTranslateOnly(Gf.Vec3d(*[float(v) for v in cam["position"]]))
        ocam = stage.GetPrimAtPath("/RackCam_B")
        xfo = UsdGeom.Xformable(ocam)
        xfo.ClearXformOpOrder()
        xfo.AddTransformOp().Set(M)
        UsdGeom.Camera(ocam).GetFocalLengthAttr().Set(float(cam["focal_length"]))

        # Table camera = exact live operator-approved view captured 2026-07-24.
        # Keep this beside the other pinned camera poses so reopening the USD,
        # restarting Isaac, or resetting the scene cannot silently restore the
        # older table-camera translation from the base layer.
        TABLE_CAM = "/Cam_Table"
        table_translation = (
            4.457081837696651,
            -7.270179168336405,
            3.0919603097311343,
        )
        table_rotation_yxz_deg = (
            -1.8111312,
            7.8956955e-14,
            89.84862,
        )
        table_focal_length_mm = 11.0
        table_clipping_range_m = (1.0, 1_000_000.0)
        table_prim = stage.GetPrimAtPath(TABLE_CAM)
        if not table_prim.IsValid() or not table_prim.IsA(UsdGeom.Camera):
            raise RuntimeError("hardened table camera is missing: " + TABLE_CAM)
        table_camera = UsdGeom.Camera(table_prim)
        table_xform = UsdGeom.Xformable(table_prim)
        table_xform.ClearXformOpOrder()
        table_xform.AddTranslateOp(
            precision=UsdGeom.XformOp.PrecisionDouble
        ).Set(Gf.Vec3d(*table_translation))
        table_xform.AddRotateYXZOp(
            precision=UsdGeom.XformOp.PrecisionFloat
        ).Set(Gf.Vec3f(*table_rotation_yxz_deg))
        table_xform.AddScaleOp(
            precision=UsdGeom.XformOp.PrecisionFloat
        ).Set(Gf.Vec3f(1.0, 1.0, 1.0))
        table_camera.GetFocalLengthAttr().Set(table_focal_length_mm)
        table_camera.GetClippingRangeAttr().Set(
            Gf.Vec2f(*table_clipping_range_m)
        )
    
        # clear ALL legacy viewport-coupled camera graphs (no-ops on a fresh boot)
        for gp in [
            "/ROS_WristCam",
            "/ROS_OutsideCam",
            "/ROS_TableCam",
            "/ROS_RackCam",
            "/ROS_InspectCam",
            "/ROS_CamsRP",
        ]:
            if stage.GetPrimAtPath(gp).IsValid():
                stage.RemovePrim(gp)
                print("removed legacy cam graph", gp, flush=True)
    
        # Viewport-independent render products (render every frame, GUI-agnostic).
        # Render budget: five+ full-res products starve the pipeline (~8Hz, some
        # silent).  Capture follows the native-DROID 320x180 contract and uses
        # Isaac's camera sensor tick rate rather than wall-clock sampling.
        if camera_profile == "capture":
            WCAM_R = "/Workcell/Franka_Right/panda_hand/WristCam"
            OCAM_R = "/RackCam_BR"
            capture_camera_paths = (
                WCAM,
                "/RackCam_B",
                WCAM_R,
                OCAM_R,
                TABLE_CAM,
                "/RackCam_A",
            )
            for camera_path in capture_camera_paths:
                camera_prim = stage.GetPrimAtPath(camera_path)
                if not camera_prim.IsValid():
                    raise RuntimeError("capture camera is missing: " + camera_path)
                camera_prim.ApplyAPI("OmniSensorAPI")
                tick_rate = camera_prim.GetAttribute("omni:sensor:tickRate")
                if not tick_rate.IsValid():
                    raise RuntimeError(
                        "OmniSensorAPI did not create tickRate on " + camera_path
                    )
                tick_rate.Set(30.0)
            rp_w = rep.create.render_product(WCAM, (320, 180))
            rp_o = rep.create.render_product("/RackCam_B", (320, 180))
            rp_wr = rep.create.render_product(WCAM_R, (320, 180))
            rp_or = rep.create.render_product(OCAM_R, (320, 180))
            rp_t = rep.create.render_product(TABLE_CAM, (320, 180))
            rp_r = rep.create.render_product("/RackCam_A", (320, 180))
            # Keep the native-DROID outside/inspect stream untouched.  The
            # verifier gets a separate moderate-resolution render product so
            # its tote crop contains enough real pixels to distinguish a
            # raised object from the permanent flat colored pad.
            rp_inspect_vlm = rep.create.render_product(
                "/RackCam_B",
                (640, 360),
            )
            paths = {
                "wrist": rp_w.path,
                "outside": rp_o.path,
                "wrist_right": rp_wr.path,
                "outside_right": rp_or.path,
                "table": rp_t.path,
                # inspect_cam is a second ROS publisher on the certified
                # outside render product; it does not consume another render.
                "inspect": rp_o.path,
                "rack": rp_r.path,
            }
            table_resolution = (320, 180)
            inspect_vlm_resolution = (640, 360)
        else:
            rp_w = rep.create.render_product(WCAM, (1280, 720))
            rp_o = rep.create.render_product("/RackCam_B", (1280, 720))
            rp_r = rep.create.render_product("/RackCam_A", (512, 288))
            # A moderate table resolution avoids adding another full-resolution
            # render product to the already multi-camera production profile.
            rp_t = rep.create.render_product(TABLE_CAM, (640, 360))
            paths = {
                "wrist": rp_w.path,
                "outside": rp_o.path,
                "rack": rp_r.path,
                "inspect": rp_o.path,
                "table": rp_t.path,
            }
            table_resolution = (640, 360)
            # Production already renders RackCam_B at 1280x720, so the VLM
            # topic can share that product without adding render cost.
            rp_inspect_vlm = rp_o
            inspect_vlm_resolution = (1280, 720)
            # Right workcell cameras use their own serving domain.
            WCAM_R = "/Workcell/Franka_Right/panda_hand/WristCam"
            if (
                stage.GetPrimAtPath(WCAM_R).IsValid()
                and stage.GetPrimAtPath("/RackCam_BR").IsValid()
            ):
                rp_wr = rep.create.render_product(WCAM_R, (960, 540))
                rp_or = rep.create.render_product("/RackCam_BR", (960, 540))
                paths["wrist_right"] = rp_wr.path
                paths["outside_right"] = rp_or.path

        vlm_paths = {"inspect_vlm": rp_inspect_vlm.path}
        published_paths = dict(paths)
        published_paths.update(vlm_paths)
    
        keys = og.Controller.Keys
        nodes = [("Tick", "omni.graph.action.OnTick")]
        connects = []
        values = []
        for prefix in list(published_paths.keys()):
            rgb, info = "rgb_" + prefix, "info_" + prefix
            nodes += [(rgb, "isaacsim.ros2.bridge.ROS2CameraHelper"),
                      (info, "isaacsim.ros2.bridge.ROS2CameraInfoHelper")]
            connects += [("Tick.outputs:tick", rgb + ".inputs:execIn"),
                         ("Tick.outputs:tick", info + ".inputs:execIn")]
            values += [(rgb + ".inputs:renderProductPath", published_paths[prefix]),
                       (rgb + ".inputs:topicName", prefix + "_cam/image_raw"),
                       (rgb + ".inputs:frameId", prefix + "_cam"),
                       (rgb + ".inputs:type", "rgb"),
                       (info + ".inputs:renderProductPath", published_paths[prefix]),
                       (info + ".inputs:topicName", prefix + "_cam/camera_info"),
                       (info + ".inputs:frameId", prefix + "_cam")]
        (g, _, _, _) = og.Controller.edit(
            {"graph_path": "/ROS_CamsRP", "evaluator_name": "push",
             "pipeline_stage": og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_ONDEMAND},
            {keys.CREATE_NODES: nodes, keys.CONNECT: connects, keys.SET_VALUES: values})
        og.Controller.evaluate_sync(g)

        if not stage.GetPrimAtPath("/ROS_CamsRP").IsValid():
            raise RuntimeError("replicator camera graph was not created")
        for product_name, product_path in published_paths.items():
            if not stage.GetPrimAtPath(product_path).IsValid():
                raise RuntimeError(
                    "render product is missing for %s: %s"
                    % (product_name, product_path)
                )
        actual_ops = {
            str(op.GetOpName()): tuple(float(value) for value in op.Get())
            for op in table_xform.GetOrderedXformOps()
        }
        expected_ops = {
            "xformOp:translate": table_translation,
            "xformOp:rotateYXZ": table_rotation_yxz_deg,
            "xformOp:scale": (1.0, 1.0, 1.0),
        }
        # rotateYXZ is authored as a USD float op.  Reading it back therefore
        # includes the expected float32 round-trip (for example 89.84862 is
        # returned as 89.8486175537).  Validate tightly in the units of each
        # op without demanding impossible decimal equality from that float op.
        op_tolerances = {
            "xformOp:translate": 1e-8,
            "xformOp:rotateYXZ": 1e-5,
            "xformOp:scale": 1e-6,
        }
        if set(actual_ops) != set(expected_ops) or any(
            max(
                abs(actual - expected)
                for actual, expected in zip(
                    actual_ops[op_name],
                    expected_value,
                )
            )
            > op_tolerances[op_name]
            for op_name, expected_value in expected_ops.items()
        ):
            raise RuntimeError(
                "table camera pose did not apply: actual=%s expected=%s"
                % (actual_ops, expected_ops)
            )
        if (
            abs(
                float(table_camera.GetFocalLengthAttr().Get())
                - table_focal_length_mm
            )
            > 1e-6
        ):
            raise RuntimeError("table camera focal length did not apply")
        globals()["_IC_TABLE_CAM_CONTRACT"] = {
            "prim": TABLE_CAM,
            "translation": table_translation,
            "rotation_yxz_deg": table_rotation_yxz_deg,
            "scale": (1.0, 1.0, 1.0),
            "focal_length_mm": table_focal_length_mm,
            "clipping_range_m": table_clipping_range_m,
            "topic": "/table_cam/image_raw",
            "camera_info_topic": "/table_cam/camera_info",
            "resolution": table_resolution,
            "render_product": paths["table"],
            "camera_profile": camera_profile,
        }
        expected_image_topics = {
            "wrist": "/wrist_cam/image_raw",
            "outside": "/outside_cam/image_raw",
            "wrist_right": "/wrist_right_cam/image_raw",
            "outside_right": "/outside_right_cam/image_raw",
            "table": "/table_cam/image_raw",
            "inspect": "/inspect_cam/image_raw",
            "rack": "/rack_cam/image_raw",
        }
        expected_camera_info_topics = {
            "wrist": "/wrist_cam/camera_info",
            "outside": "/outside_cam/camera_info",
            "wrist_right": "/wrist_right_cam/camera_info",
            "outside_right": "/outside_right_cam/camera_info",
            "table": "/table_cam/camera_info",
            "inspect": "/inspect_cam/camera_info",
            "rack": "/rack_cam/camera_info",
        }
        if set(paths) != set(expected_image_topics):
            raise RuntimeError(
                "full camera topic contract is incomplete: actual=%s expected=%s"
                % (sorted(paths), sorted(expected_image_topics))
            )
        globals()["_IC_CAMERA_TOPIC_CONTRACT"] = {
            "camera_profile": camera_profile,
            "image_topics": expected_image_topics,
            "camera_info_topics": expected_camera_info_topics,
            "render_products": dict(paths),
            "unique_render_product_count": len(set(paths.values())),
        }
        if globals()["_IC_CAMERA_TOPIC_CONTRACT"][
            "unique_render_product_count"
        ] != 6:
            raise RuntimeError(
                "full camera contract must use exactly six render products: %s"
                % globals()["_IC_CAMERA_TOPIC_CONTRACT"]
            )
        globals()["_IC_VLM_CAMERA_TOPIC_CONTRACT"] = {
            "camera_profile": camera_profile,
            "image_topics": {
                "inspect_vlm": "/inspect_vlm_cam/image_raw",
            },
            "camera_info_topics": {
                "inspect_vlm": "/inspect_vlm_cam/camera_info",
            },
            "render_products": dict(vlm_paths),
            "resolution": {
                "inspect_vlm": inspect_vlm_resolution,
            },
            "additional_render_product_count": len(
                set(published_paths.values()) - set(paths.values())
            ),
        }
        _expected_additional_products = 1 if camera_profile == "capture" else 0
        if globals()["_IC_VLM_CAMERA_TOPIC_CONTRACT"][
            "additional_render_product_count"
        ] != _expected_additional_products:
            raise RuntimeError(
                "VLM camera render-product contract is invalid: %s"
                % globals()["_IC_VLM_CAMERA_TOPIC_CONTRACT"]
            )
        globals()["_IC_CAMS_RP_READY"] = True
    
        print(
            "IC_CAMS_RP_BUILT profile=%s products=%s "
            "table_topic=/table_cam/image_raw table_resolution=%dx%d "
            "vlm_topic=/inspect_vlm_cam/image_raw vlm_resolution=%dx%d "
            "viewport_independent=true"
            % (
                camera_profile,
                sorted(paths),
                table_resolution[0],
                table_resolution[1],
                inspect_vlm_resolution[0],
                inspect_vlm_resolution[1],
            ),
            flush=True,
        )
    except Exception:
        globals()["_IC_CAMS_RP_READY"] = False
        globals()["_IC_TABLE_CAM_CONTRACT"] = None
        globals()["_IC_CAMERA_TOPIC_CONTRACT"] = None
        globals()["_IC_VLM_CAMERA_TOPIC_CONTRACT"] = None
        print("IC_CAMS_RP_ERR:\n" + traceback.format_exc(), flush=True)
        raise

_ic_cams_rp_build()
del _ic_cams_rp_build
