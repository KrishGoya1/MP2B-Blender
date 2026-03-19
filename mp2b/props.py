# mp2b_mediapipe2blender/mp2b/props.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
from . import state
from . import video


def _sync_cfg_from_scene():
    """
    Periodic config snapshot for worker threads (video).
    Must be robust during addon enable/disable and file loading.
    """
    try:
        sc = bpy.context.scene
    except Exception:
        return 0.25

    if sc is None:
        return 0.25

    try:
        state.cfg_set(
            running=bool(getattr(sc, "m2b_running", False)),
            enable_feed=bool(getattr(sc, "m2b_enable_feed", True)),
            video_source=str(getattr(sc, "m2b_video_source", "SHM")),
            video_scale=str(getattr(sc, "m2b_video_scale", "1.0")),
            video_fps_cap=float(getattr(sc, "m2b_video_fps_cap", state.UPLOAD_FPS_CAP) or state.UPLOAD_FPS_CAP),
            ingest_mode=str(getattr(sc, "m2b_ingest_mode", "MATCH_UPLOAD")),
            ingest_fps_cap=float(getattr(sc, "m2b_ingest_fps_cap", state.UPLOAD_FPS_CAP) or state.UPLOAD_FPS_CAP),
            shm_name=str((getattr(sc, "m2b_shm_name", "mp2bl_frame") or "mp2bl_frame")).strip() or "mp2bl_frame",
            mjpeg_url=str((getattr(sc, "m2b_mjpeg_url", "") or "")).strip(),
            host=str((getattr(sc, "m2b_host", "0.0.0.0") or "0.0.0.0")).strip() or "0.0.0.0",
            port=int(getattr(sc, "m2b_port", 5001)),
        )
    except Exception:
        # Silent by design: props updates can happen during teardown / partial init.
        pass

    return 0.25


def on_enable_feed_update(self, context):
    _sync_cfg_from_scene()
    sc = context.scene

    if bool(getattr(sc, "m2b_running", False)):
        video.restart_video_pipeline_if_needed()
        return

    # Not running: keep UI behavior consistent (no worker thread).
    if not bool(getattr(sc, "m2b_enable_feed", True)):
        video.video_off_hard()
        return

    cam = video.get_active_camera()
    video.cleanup_m2b_slots(cam)
    try:
        if cam:
            cam.data.show_background_images = True
    except Exception:
        pass


def on_video_source_update(self, context):
    _sync_cfg_from_scene()
    sc = context.scene
    if bool(getattr(sc, "m2b_running", False)) and bool(getattr(sc, "m2b_enable_feed", True)):
        video.restart_video_pipeline_if_needed()


def on_mjpeg_url_update(self, context):
    _sync_cfg_from_scene()
    sc = context.scene
    if (
        str(getattr(sc, "m2b_video_source", "SHM")) == "MJPEG"
        and bool(getattr(sc, "m2b_running", False))
        and bool(getattr(sc, "m2b_enable_feed", True))
    ):
        video.restart_video_pipeline_if_needed()


def on_shm_name_update(self, context):
    _sync_cfg_from_scene()
    sc = context.scene
    if (
        str(getattr(sc, "m2b_video_source", "SHM")) == "SHM"
        and bool(getattr(sc, "m2b_running", False))
        and bool(getattr(sc, "m2b_enable_feed", True))
    ):
        video.restart_video_pipeline_if_needed()


def on_video_scale_update(self, context):
    _sync_cfg_from_scene()
    sc = context.scene
    if bool(getattr(sc, "m2b_running", False)) and bool(getattr(sc, "m2b_enable_feed", True)):
        video.force_recreate_texture_next_upload()


def on_ingest_mode_update(self, context):
    _sync_cfg_from_scene()
    return


def register_props():
    bpy.types.Scene.m2b_host = bpy.props.StringProperty(default="0.0.0.0")
    bpy.types.Scene.m2b_port = bpy.props.IntProperty(default=5001, min=1, max=65535)

    bpy.types.Scene.m2b_axis_scale_x = bpy.props.FloatProperty(default=1.0)
    bpy.types.Scene.m2b_axis_scale_y = bpy.props.FloatProperty(default=1.0)
    bpy.types.Scene.m2b_axis_scale_z = bpy.props.FloatProperty(default=1.0)

    bpy.types.Scene.m2b_pos_x = bpy.props.FloatProperty(default=0.0)
    bpy.types.Scene.m2b_pos_y = bpy.props.FloatProperty(default=0.0)
    bpy.types.Scene.m2b_pos_z = bpy.props.FloatProperty(default=0.0)

    bpy.types.Scene.m2b_rot_x = bpy.props.FloatProperty(default=0.0)
    bpy.types.Scene.m2b_rot_y = bpy.props.FloatProperty(default=0.0)
    bpy.types.Scene.m2b_rot_z = bpy.props.FloatProperty(default=0.0)

    bpy.types.Scene.m2b_aspect = bpy.props.FloatProperty(default=1.7777778, min=0.1, max=10.0)
    bpy.types.Scene.m2b_face_height = bpy.props.FloatProperty(default=1.6)
    bpy.types.Scene.m2b_hands_height = bpy.props.FloatProperty(default=1.0)
    bpy.types.Scene.m2b_pose_depth_scale = bpy.props.FloatProperty(default=1.0)

    bpy.types.Scene.m2b_enable_feed = bpy.props.BoolProperty(default=True, update=on_enable_feed_update)

    bpy.types.Scene.m2b_video_source = bpy.props.EnumProperty(
        name="Video Source",
        items=[
            ("SHM", "Shared Memory", "Fastest: reads raw RGB from shared memory written by the client"),
            ("MJPEG", "MJPEG URL", "Fallback: reads MJPEG stream via OpenCV VideoCapture"),
        ],
        default="SHM",
        update=on_video_source_update,
    )

    bpy.types.Scene.m2b_video_scale = bpy.props.EnumProperty(
        name="Output Scale",
        items=[
            ("1.0", "100%", "No downscale"),
            ("0.75", "75%", "Downscale to 75% (needs OpenCV for best quality)"),
            ("0.5", "50%", "Downscale to 50% (fast path)"),
            ("0.33", "33%", "Downscale to 33% (needs OpenCV for best quality)"),
            ("0.25", "25%", "Downscale to 25% (fast path)"),
        ],
        default="1.0",
        update=on_video_scale_update,
    )

    bpy.types.Scene.m2b_video_fps_cap = bpy.props.FloatProperty(
        name="Blender Upload FPS",
        default=30.0,
        min=1.0,
        max=60.0,
    )

    bpy.types.Scene.m2b_ingest_mode = bpy.props.EnumProperty(
        name="Ingest Mode",
        items=[
            ("MATCH_UPLOAD", "Match Upload", "Ingest is throttled to Blender Upload FPS"),
            ("FIXED", "Fixed", "Use a separate ingest FPS cap"),
        ],
        default="MATCH_UPLOAD",
        update=on_ingest_mode_update,
    )

    bpy.types.Scene.m2b_ingest_fps_cap = bpy.props.FloatProperty(
        name="Ingest FPS",
        default=30.0,
        min=1.0,
        max=60.0,
        update=on_ingest_mode_update,
    )

    bpy.types.Scene.m2b_shm_name = bpy.props.StringProperty(
        name="SHM Name",
        default="mp2bl_frame",
        update=on_shm_name_update,
    )

    bpy.types.Scene.m2b_mjpeg_url = bpy.props.StringProperty(
        default="http://127.0.0.1:8099/stream.mjpg",
        update=on_mjpeg_url_update,
    )

    bpy.types.Scene.m2b_running = bpy.props.BoolProperty(default=False)

    # Timer cfg sync (worker reads cfg snapshot)
    try:
        if not bpy.app.timers.is_registered(_sync_cfg_from_scene):
            bpy.app.timers.register(_sync_cfg_from_scene, first_interval=0.0)
    except Exception:
        pass

    try:
        _sync_cfg_from_scene()
    except Exception:
        pass


def unregister_props():
    try:
        if bpy.app.timers.is_registered(_sync_cfg_from_scene):
            bpy.app.timers.unregister(_sync_cfg_from_scene)
    except Exception:
        pass

    for p in [
        "m2b_host",
        "m2b_port",
        "m2b_axis_scale_x",
        "m2b_axis_scale_y",
        "m2b_axis_scale_z",
        "m2b_pos_x",
        "m2b_pos_y",
        "m2b_pos_z",
        "m2b_rot_x",
        "m2b_rot_y",
        "m2b_rot_z",
        "m2b_aspect",
        "m2b_face_height",
        "m2b_hands_height",
        "m2b_pose_depth_scale",
        "m2b_enable_feed",
        "m2b_video_source",
        "m2b_video_scale",
        "m2b_video_fps_cap",
        "m2b_ingest_mode",
        "m2b_ingest_fps_cap",
        "m2b_shm_name",
        "m2b_mjpeg_url",
        "m2b_running",
    ]:
        if hasattr(bpy.types.Scene, p):
            try:
                delattr(bpy.types.Scene, p)
            except Exception:
                pass
