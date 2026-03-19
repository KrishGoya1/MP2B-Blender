# mp2b_mediapipe2blender/mp2b/state.py
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import time
import struct

# --- OpenCV optional ---
try:
    import cv2  # type: ignore
except Exception:
    cv2 = None


# -----------------------------
# UDP tracking protocol
MAGIC = b"MP2B"
VER = 1
MODEL_POSE = 1
MODEL_HANDS = 2
MODEL_FACE = 3

HDR_FMT = "<4s B B I B B B H B"
HDR_SIZE = struct.calcsize(HDR_FMT)

REASM_TIMEOUT = 0.5
HAND_OVERLAP_THRESHOLD = 0.02


# -----------------------------
# SHM protocol (MUST match client)
SHM_MAGIC = b"M2BS"
SHM_VER = 1
SHM_FMT_RGB24 = 1
SHM_HDR_FMT = "<4s B B H H H I I I I I I 28s"
SHM_HDR_SIZE = struct.calcsize(SHM_HDR_FMT)
SHM_PIX_OFFS = 64

_shm_module_ok = None


def lazy_import_shm():
    global _shm_module_ok
    if _shm_module_ok is True:
        return True
    if _shm_module_ok is False:
        return False
    try:
        from multiprocessing import shared_memory as _sm  # noqa: F401
        _shm_module_ok = True
        return True
    except Exception:
        _shm_module_ok = False
        return False


def mono_ms() -> int:
    return int(time.monotonic() * 1000.0)


# -----------------------------
# Error channel (NO print; UI/Operator can surface this)
_err_lock = threading.Lock()
_last_error_msg = ""
_last_error_ts = 0.0
_MAX_ERR_LEN = 500  # keep UI/self.report readable; avoids runaway strings


def set_last_error(msg: str):
    """
    Store latest error message for UI/operator. Keep it short.
    Best-effort: dedupe identical messages to reduce lock churn/spam.
    """
    global _last_error_msg, _last_error_ts
    if not msg:
        return

    s = str(msg).strip()
    if not s:
        return
    if len(s) > _MAX_ERR_LEN:
        s = s[:_MAX_ERR_LEN] + "…"

    with _err_lock:
        if s == _last_error_msg:
            return
        _last_error_msg = s
        _last_error_ts = time.time()


def get_last_error():
    """Returns (msg, ts). If msg is empty, ts may be 0.0."""
    with _err_lock:
        return _last_error_msg, float(_last_error_ts)


def clear_last_error():
    global _last_error_msg, _last_error_ts
    with _err_lock:
        _last_error_msg = ""
        _last_error_ts = 0.0


# -----------------------------
# Mesh specs
SPECS = [
    ("pose", "PoseMesh", 33, "PoseMeshCollection"),
    ("face", "FaceMesh", 468, "FaceMeshCollection"),
    ("left", "LeftHandMesh", 21, "LeftHandMeshCollection"),
    ("right", "RightHandMesh", 21, "RightHandMeshCollection"),
]
KEY_COUNTS = {k: n for (k, _, n, _) in SPECS}


# -----------------------------
# Tracking state
server_thread = None

data_lock = threading.Lock()
raw_coords = {}
mesh_objects = {}
obj_objects = {}
need_update = False
dirty_keys = set()
visible = {}
last_seq_map = {"pose": -1, "hands": -1, "face": -1}
last_seq_time = {"pose": 0.0, "hands": 0.0, "face": 0.0}
reasm = {}
_prev_coords = {"left": None, "right": None}


# -----------------------------
# Video state
feed_running = False
webcam_texture = None

_latest_frame_rgb_u8 = None
_latest_frame_seq = 0
_uploaded_frame_seq = -1
_frame_size = (0, 0)

_float_buffer = None

_video_thread = None
_video_stop = threading.Event()
_video_lock = threading.Lock()

_mjpeg_cap = None
_mjpeg_cap_lock = threading.Lock()

_shm_handle = None
_shm_last_name = ""

# BG slot tracking
M2B_IMG_NAME = "M2B_WebcamTexture"
CAM_SLOT_KEY = "m2b_bg_index"

UPLOAD_FPS_CAP = 30.0
_last_upload_ts = 0.0


# -----------------------------
# Stats (best-effort)
_stats_lock = threading.Lock()
_stat_ingest_fps = 0.0
_stat_upload_fps = 0.0
_stat_last_ingest_t = 0.0
_stat_last_upload_t = 0.0
_stat_bg_dup_cleaned = 0


# -----------------------------
# Thread-safe cfg snapshot for workers
_cfg_lock = threading.Lock()
_cfg = {
    "running": False,
    "enable_feed": True,
    "video_source": "SHM",
    "video_scale": "1.0",
    "video_fps_cap": 30.0,
    "ingest_mode": "MATCH_UPLOAD",
    "ingest_fps_cap": 30.0,
    "shm_name": "mp2bl_frame",
    "mjpeg_url": "http://127.0.0.1:8099/stream.mjpg",
    "host": "0.0.0.0",
    "port": 5001,
}


def cfg_get():
    with _cfg_lock:
        return dict(_cfg)


def cfg_set(**kwargs):
    with _cfg_lock:
        _cfg.update(kwargs)
