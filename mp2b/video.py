# mp2b_mediapipe2blender/mp2b/video.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
import time
import numpy as np
import struct

from . import state


# -----------------------------------------------------------------------------
# Robust ID for MP2B image datablock (prevents duplicates after .blend reload)
# -----------------------------------------------------------------------------
# We tag the Image datablock so it's recognizable even if Blender renames it
# to "NAME.001" when a same-named datablock already exists in the file.
_M2B_IMG_TAG_KEY = "m2b_is_mp2b_image"


def _tag_image_as_m2b(img):
    try:
        if img is not None:
            img[_M2B_IMG_TAG_KEY] = True
    except Exception:
        pass


def _is_tagged_m2b_image(img) -> bool:
    try:
        return bool(img is not None and img.get(_M2B_IMG_TAG_KEY, False))
    except Exception:
        return False


def _is_m2b_image_name(img) -> bool:
    """Fallback: tolerate Blender suffix renames like 'NAME.001'."""
    try:
        if img is None:
            return False
        nm = str(getattr(img, "name", "") or "")
        base = str(getattr(state, "M2B_IMG_NAME", "") or "")
        if not base:
            return False
        if nm == base:
            return True
        # tolerate suffix ".001" etc
        if nm.startswith(base + "."):
            suf = nm[len(base) + 1:]
            return suf.isdigit()
        return False
    except Exception:
        return False


def _find_existing_m2b_image():
    """
    Search an existing MP2B Image datablock in the blend:
    1) tagged image
    2) exact name
    3) suffixed name (NAME.001 etc)
    """
    try:
        # 1) tagged wins
        for img in bpy.data.images:
            if _is_tagged_m2b_image(img):
                return img
    except Exception:
        pass

    # 2) exact name
    try:
        base = str(getattr(state, "M2B_IMG_NAME", "") or "")
        if base:
            img = bpy.data.images.get(base)
            if img is not None:
                _tag_image_as_m2b(img)
                return img
    except Exception:
        pass

    # 3) suffixed name
    try:
        for img in bpy.data.images:
            if _is_m2b_image_name(img):
                _tag_image_as_m2b(img)
                return img
    except Exception:
        pass

    return None


# -----------------------------------------------------------------------------
# ---------------- Camera helpers (main thread)
# -----------------------------------------------------------------------------
def find_any_camera_object():
    sc = bpy.context.scene
    cam = getattr(sc, "camera", None)
    if cam and cam.type == "CAMERA":
        return cam
    try:
        for ob in bpy.context.view_layer.objects:
            if ob.type == "CAMERA":
                return ob
    except Exception:
        pass
    for ob in bpy.data.objects:
        if ob.type == "CAMERA":
            return ob
    return None


def get_active_camera():
    sc = bpy.context.scene
    cam = getattr(sc, "camera", None)
    if cam and cam.type == "CAMERA":
        return cam
    cam2 = find_any_camera_object()
    if cam2 and cam2.type == "CAMERA":
        try:
            sc.camera = cam2
        except Exception:
            pass
        return cam2
    return None


def bg_images(cam):
    if cam is None:
        return None
    try:
        return getattr(cam.data, "background_images", None)
    except Exception:
        return None


def is_m2b_slot(slot) -> bool:
    """
    Robust slot detection: prefer tag; tolerate suffix renames.
    """
    try:
        img = getattr(slot, "image", None)
        if img is None:
            return False
        if _is_tagged_m2b_image(img):
            return True
        # fallback for old projects: name-based detection
        return _is_m2b_image_name(img) or (str(getattr(img, "name", "")) == str(state.M2B_IMG_NAME))
    except Exception:
        return False


def cleanup_m2b_slots(cam):
    if cam is None:
        return
    bg = bg_images(cam)
    if not bg:
        try:
            if state.CAM_SLOT_KEY in cam.data:
                del cam.data[state.CAM_SLOT_KEY]
        except Exception:
            pass
        return

    keep_idx = -1
    try:
        keep_idx = int(cam.data.get(state.CAM_SLOT_KEY, -1))
    except Exception:
        keep_idx = -1

    if not (0 <= keep_idx < len(bg) and is_m2b_slot(bg[keep_idx])):
        keep_idx = -1

    if keep_idx < 0:
        for i in range(len(bg)):
            if is_m2b_slot(bg[i]):
                keep_idx = i
                break

    to_remove = []
    for i in range(len(bg)):
        if i == keep_idx:
            continue
        if is_m2b_slot(bg[i]):
            to_remove.append(i)

    if to_remove:
        with state._stats_lock:
            state._stat_bg_dup_cleaned += len(to_remove)

    for i in reversed(to_remove):
        try:
            bg.remove(bg[i])
        except Exception:
            try:
                bg[i].image = None
            except Exception:
                pass

    new_keep = -1
    for i in range(len(bg)):
        if is_m2b_slot(bg[i]):
            new_keep = i
            break

    try:
        if new_keep >= 0:
            cam.data[state.CAM_SLOT_KEY] = int(new_keep)
        else:
            if state.CAM_SLOT_KEY in cam.data:
                del cam.data[state.CAM_SLOT_KEY]
    except Exception:
        pass


def cleanup_all_cameras_m2b_slots():
    try:
        for ob in bpy.data.objects:
            if ob.type == "CAMERA":
                cleanup_m2b_slots(ob)
    except Exception:
        pass


def get_or_create_m2b_slot(cam):
    if cam is None:
        return None
    bg = bg_images(cam)
    if bg is None:
        return None

    cleanup_m2b_slots(cam)

    idx = -1
    try:
        idx = int(cam.data.get(state.CAM_SLOT_KEY, -1))
    except Exception:
        idx = -1

    if 0 <= idx < len(bg) and is_m2b_slot(bg[idx]):
        return bg[idx]

    for i in range(len(bg)):
        if is_m2b_slot(bg[i]):
            try:
                cam.data[state.CAM_SLOT_KEY] = int(i)
            except Exception:
                pass
            return bg[i]

    try:
        slot = bg.new()
    except Exception:
        slot = bg[0] if len(bg) else None
    if slot is None:
        return None

    try:
        for i in range(len(bg)):
            if bg[i] == slot:
                cam.data[state.CAM_SLOT_KEY] = int(i)
                break
    except Exception:
        pass

    return slot


def attach_bg_to_camera(cam):
    if cam is None or state.webcam_texture is None:
        return False

    try:
        cam.data.show_background_images = True
    except Exception:
        pass

    # Always tag our image so we can find it after reload even if renamed
    _tag_image_as_m2b(state.webcam_texture)

    slot = get_or_create_m2b_slot(cam)
    if slot is None:
        return False

    try:
        slot.source = "IMAGE"
    except Exception:
        pass
    try:
        slot.image = state.webcam_texture
    except Exception:
        return False
    try:
        slot.show_background_image = True
    except Exception:
        pass
    try:
        slot.alpha = 1.0
    except Exception:
        pass
    try:
        slot.display_depth = "BACK"
    except Exception:
        pass

    cleanup_m2b_slots(cam)
    return True


def detach_bg_from_camera(cam):
    if cam is None:
        return
    bg = bg_images(cam)
    if bg:
        for i in reversed(range(len(bg))):
            if is_m2b_slot(bg[i]):
                try:
                    bg.remove(bg[i])
                except Exception:
                    try:
                        bg[i].image = None
                    except Exception:
                        pass

    try:
        if state.CAM_SLOT_KEY in cam.data:
            del cam.data[state.CAM_SLOT_KEY]
    except Exception:
        pass

    try:
        cam.data.show_background_images = False
    except Exception:
        pass


# -----------------------------------------------------------------------------
# ---------------- Texture resources (main thread)
# -----------------------------------------------------------------------------
def create_or_resize_texture(width, height):
    """
    Create or reuse the MP2B Image datablock safely (no NAME.001 storms).
    - Prefer reusing an existing MP2B image from the blend (tagged/name/suffixed).
    - Resize in-place if possible (img.scale) to keep identity stable.
    """
    width = int(max(2, width))
    height = int(max(2, height))

    # If we already have a valid image, try to resize in-place (no new datablock)
    img = state.webcam_texture
    if img is None:
        img = _find_existing_m2b_image()
        if img is not None:
            state.webcam_texture = img

    if img is not None:
        _tag_image_as_m2b(img)
        try:
            cur_w = int(img.size[0])
            cur_h = int(img.size[1])
        except Exception:
            cur_w, cur_h = 0, 0

        if cur_w != width or cur_h != height:
            # Try to resize in-place; if not possible, recreate cleanly
            try:
                img.scale(width, height)
            except Exception:
                # Recreate: remove the existing one FIRST to avoid Blender adding suffixes.
                try:
                    bpy.data.images.remove(img)
                except Exception:
                    pass
                state.webcam_texture = None
                img = None

    if img is None:
        # Ensure no conflicting base-name image remains (best-effort)
        try:
            base = str(state.M2B_IMG_NAME)
            existing = bpy.data.images.get(base)
            if existing is not None:
                # If it's ours (tagged/name), remove it so we can recreate exactly named
                if _is_tagged_m2b_image(existing) or _is_m2b_image_name(existing) or existing.name == base:
                    try:
                        bpy.data.images.remove(existing)
                    except Exception:
                        pass
        except Exception:
            pass

        state.webcam_texture = bpy.data.images.new(
            name=state.M2B_IMG_NAME, width=width, height=height, alpha=True
        )
        _tag_image_as_m2b(state.webcam_texture)

    cam = get_active_camera()
    attach_bg_to_camera(cam)


def ensure_float_buffer(width, height):
    need = (
        state._float_buffer is None
        or state._float_buffer.size != (width * height * 4)
        or state.webcam_texture is None
    )
    if need:
        state._float_buffer = np.empty((height * width * 4,), dtype=np.float32)
        create_or_resize_texture(width, height)
        state._float_buffer[3::4] = 1.0


def free_video_resources():
    state._float_buffer = None
    state._uploaded_frame_seq = -1
    with state._video_lock:
        state._latest_frame_rgb_u8 = None
        state._frame_size = (0, 0)

    if state.webcam_texture is not None:
        try:
            bpy.data.images.remove(state.webcam_texture)
        except Exception:
            pass
        state.webcam_texture = None


def unregister_video_timer():
    try:
        if bpy.app.timers.is_registered(update_texture_timer):
            bpy.app.timers.unregister(update_texture_timer)
    except Exception:
        pass


def video_scale_factor(sc) -> float:
    v = str(getattr(sc, "m2b_video_scale", "1.0"))
    if v == "1.0":
        return 1.0
    if v == "0.75":
        return 0.75
    if v == "0.5":
        return 0.5
    if v == "0.33":
        return 0.3333333
    if v == "0.25":
        return 0.25
    return 1.0


def downscale_rgb(rgb_u8, scale: float):
    if rgb_u8 is None or scale >= 0.999:
        return rgb_u8
    h, w = rgb_u8.shape[:2]
    if h <= 2 or w <= 2:
        return rgb_u8
    if scale <= 0.251:
        return rgb_u8[::4, ::4, :]
    if 0.49 <= scale <= 0.51:
        return rgb_u8[::2, ::2, :]
    if state.cv2 is not None:
        nh = max(2, int(h * scale))
        nw = max(2, int(w * scale))
        try:
            return state.cv2.resize(rgb_u8, (nw, nh), interpolation=state.cv2.INTER_AREA)
        except Exception:
            return rgb_u8
    return rgb_u8


def update_upload_stats():
    now = time.monotonic()
    if state._stat_last_upload_t > 0.0:
        dt = now - state._stat_last_upload_t
        if dt > 0:
            fps = 1.0 / dt
            state._stat_upload_fps = (state._stat_upload_fps * 0.9) + (fps * 0.1)
    state._stat_last_upload_t = now


def update_texture_timer():
    """
    Main-thread timer: usa bpy.context.scene direttamente.
    """
    sc = bpy.context.scene

    if (not sc.m2b_running) or (not sc.m2b_enable_feed) or (not state.feed_running):
        return None

    cap_fps = float(getattr(sc, "m2b_video_fps_cap", state.UPLOAD_FPS_CAP) or state.UPLOAD_FPS_CAP)
    cap_fps = max(1.0, min(60.0, cap_fps))

    now = time.monotonic()
    min_dt = 1.0 / cap_fps
    if (now - state._last_upload_ts) < min_dt:
        return max(0.001, min_dt - (now - state._last_upload_ts))

    with state._video_lock:
        seq = state._latest_frame_seq
        rgb = state._latest_frame_rgb_u8
        w, h = state._frame_size

    if rgb is None or w == 0 or h == 0:
        state._last_upload_ts = now
        return min_dt

    if seq == state._uploaded_frame_seq:
        state._last_upload_ts = now
        return min_dt

    scale = video_scale_factor(sc)
    rgb_use = downscale_rgb(rgb, scale)
    try:
        hh, ww = rgb_use.shape[:2]
    except Exception:
        state._last_upload_ts = now
        return min_dt

    ensure_float_buffer(int(ww), int(hh))

    cam = get_active_camera()
    attach_bg_to_camera(cam)
    cleanup_m2b_slots(cam)

    try:
        rgb2 = rgb_use[::-1, :, :]
    except Exception:
        rgb2 = rgb_use

    try:
        flat = rgb2.reshape(-1, 3)
        state._float_buffer[0::4] = flat[:, 0] * (1.0 / 255.0)
        state._float_buffer[1::4] = flat[:, 1] * (1.0 / 255.0)
        state._float_buffer[2::4] = flat[:, 2] * (1.0 / 255.0)
    except Exception:
        state._last_upload_ts = now
        return min_dt

    if state.webcam_texture is not None and len(state.webcam_texture.pixels) == state._float_buffer.size:
        try:
            _tag_image_as_m2b(state.webcam_texture)
            state.webcam_texture.pixels.foreach_set(state._float_buffer)
            state.webcam_texture.update()
        except Exception:
            pass

    state._uploaded_frame_seq = seq
    state._last_upload_ts = now

    with state._stats_lock:
        update_upload_stats()

    return min_dt


# -----------------------------------------------------------------------------
# ---------------- Worker thread (uses cfg snapshot)
# -----------------------------------------------------------------------------
def shm_close():
    if state._shm_handle is not None:
        try:
            state._shm_handle.close()
        except Exception:
            pass
        state._shm_handle = None
    state._shm_last_name = ""


def shm_try_open(name: str):
    if not state.lazy_import_shm():
        return False
    try:
        from multiprocessing import shared_memory as sm
    except Exception:
        return False

    if state._shm_handle is not None and state._shm_last_name == name:
        return True

    shm_close()
    try:
        h = sm.SharedMemory(name=name, create=False)
    except Exception:
        return False

    state._shm_handle = h
    state._shm_last_name = name
    return True


def shm_write_consumer_heartbeat(buf):
    try:
        if buf is None or len(buf) < state.SHM_HDR_SIZE:
            return
        struct.pack_into("<I", buf, 28, int(state.mono_ms()) & 0xFFFFFFFF)
    except Exception:
        pass


def read_shm_header(buf):
    try:
        if buf is None or len(buf) < state.SHM_HDR_SIZE:
            return None
        h = bytes(buf[:state.SHM_HDR_SIZE])
        return struct.unpack(state.SHM_HDR_FMT, h)
    except Exception:
        return None


def shm_read_latest_frame_lockless(buf):
    try:
        h1 = read_shm_header(buf)
        if not h1:
            return None, 0, 0, None

        magic, ver, fmt, w, h, stride, frame_bytes, seqb, seqe, *_ = h1
        if magic != state.SHM_MAGIC or int(ver) != int(state.SHM_VER) or int(fmt) != int(state.SHM_FMT_RGB24):
            return None, 0, 0, None

        w = int(w)
        h = int(h)
        stride = int(stride)
        frame_bytes = int(frame_bytes)
        seqb = int(seqb)
        seqe = int(seqe)

        if w <= 0 or h <= 0 or seqb != seqe:
            return None, 0, 0, None

        if frame_bytes <= 0:
            frame_bytes = w * h * 3

        need_total = state.SHM_PIX_OFFS + frame_bytes
        if len(buf) < need_total:
            return None, 0, 0, None

        pix_mv = buf[state.SHM_PIX_OFFS:state.SHM_PIX_OFFS + frame_bytes]

        h2 = read_shm_header(buf)
        if not h2:
            return None, 0, 0, None

        magic2, ver2, fmt2, w2, h2v, stride2, frame_bytes2, seqb2, seqe2, *_ = h2
        if magic2 != state.SHM_MAGIC or int(ver2) != int(state.SHM_VER) or int(fmt2) != int(state.SHM_FMT_RGB24):
            return None, 0, 0, None
        if int(w2) != w or int(h2v) != h:
            return None, 0, 0, None
        if int(seqb2) != int(seqe2) or int(seqb2) != seqb:
            return None, 0, 0, None

        if stride == w * 3 and frame_bytes == w * h * 3:
            arr = np.frombuffer(pix_mv, dtype=np.uint8).reshape((h, w, 3)).copy()
        else:
            row_bytes = w * 3
            arr = np.empty((h, w, 3), dtype=np.uint8)
            mv_len = len(pix_mv)
            for y in range(h):
                src_off = y * stride
                end_off = src_off + row_bytes
                if end_off > mv_len:
                    return None, 0, 0, None
                row = np.frombuffer(pix_mv[src_off:end_off], dtype=np.uint8).reshape((w, 3))
                arr[y, :, :] = row

        return seqb, w, h, arr
    except Exception:
        return None, 0, 0, None


def update_ingest_stats():
    now = time.monotonic()
    if state._stat_last_ingest_t > 0.0:
        dt = now - state._stat_last_ingest_t
        if dt > 0:
            fps = 1.0 / dt
            state._stat_ingest_fps = (state._stat_ingest_fps * 0.9) + (fps * 0.1)
    state._stat_last_ingest_t = now


def effective_ingest_cap(cfg) -> float:
    cap = float(cfg.get("video_fps_cap", state.UPLOAD_FPS_CAP) or state.UPLOAD_FPS_CAP)
    cap = max(1.0, min(60.0, cap))
    mode = str(cfg.get("ingest_mode", "MATCH_UPLOAD"))
    if mode == "FIXED":
        c2 = float(cfg.get("ingest_fps_cap", cap) or cap)
        return max(1.0, min(60.0, c2))
    return cap


def close_mjpeg_cap(local_cap):
    try:
        if local_cap is not None:
            local_cap.release()
    except Exception:
        pass


def publish_mjpeg_cap(new_cap):
    with state._mjpeg_cap_lock:
        state._mjpeg_cap = new_cap


def video_worker():
    """
    Worker thread.
    OpenCV cap.read() can raise cv2.error (not only return ok=False).
    We catch it and treat as stream failure -> reset capture -> continue.
    No prints.
    """
    cap = None
    last_url = ""
    last_ingest_t = 0.0

    while not state._video_stop.is_set():
        cfg = state.cfg_get()

        if (not cfg.get("running", False)) or (not cfg.get("enable_feed", True)) or (not state.feed_running):
            try:
                if state._shm_handle is not None:
                    shm_write_consumer_heartbeat(state._shm_handle.buf)
            except Exception:
                pass
            time.sleep(0.05)
            continue

        src = str(cfg.get("video_source", "SHM"))
        if src not in ("SHM", "MJPEG"):
            src = "SHM"

        ingest_cap = effective_ingest_cap(cfg)
        now = time.monotonic()
        min_dt = 1.0 / ingest_cap
        if (now - last_ingest_t) < min_dt:
            time.sleep(max(0.0005, min_dt - (now - last_ingest_t)))
            continue
        last_ingest_t = time.monotonic()

        # -------- SHM --------
        if src == "SHM":
            nm = str(cfg.get("shm_name", "mp2bl_frame") or "mp2bl_frame").strip() or "mp2bl_frame"
            if not shm_try_open(nm) or state._shm_handle is None:
                if cap is not None:
                    close_mjpeg_cap(cap)
                    cap = None
                    publish_mjpeg_cap(None)
                time.sleep(0.03)
                continue

            buf = state._shm_handle.buf
            shm_write_consumer_heartbeat(buf)

            seq, w, h, arr = shm_read_latest_frame_lockless(buf)
            if arr is None or seq is None:
                time.sleep(0.002)
                continue

            try:
                state.clear_last_error()
            except Exception:
                pass

            with state._video_lock:
                if int(seq) == int(state._latest_frame_seq):
                    time.sleep(0.001)
                    continue
                state._latest_frame_rgb_u8 = arr
                state._latest_frame_seq = int(seq)
                state._frame_size = (int(w), int(h))

            with state._stats_lock:
                update_ingest_stats()

            time.sleep(0.0005)
            continue

        # -------- MJPEG --------
        url = str(cfg.get("mjpeg_url", "") or "").strip()
        if not url:
            if cap is not None:
                close_mjpeg_cap(cap)
                cap = None
                publish_mjpeg_cap(None)
            time.sleep(0.03)
            continue

        if state.cv2 is None:
            time.sleep(0.10)
            continue

        if url != last_url:
            last_url = url
            close_mjpeg_cap(cap)
            cap = None
            publish_mjpeg_cap(None)

        if cap is None or (hasattr(cap, "isOpened") and not cap.isOpened()):
            try:
                cap = state.cv2.VideoCapture(url)
            except Exception as e:
                cap = None
                try:
                    state.set_last_error(f"MJPEG open failed: {e}")
                except Exception:
                    pass

            if cap is None or (hasattr(cap, "isOpened") and not cap.isOpened()):
                close_mjpeg_cap(cap)
                cap = None
                publish_mjpeg_cap(None)
                time.sleep(0.15)
                continue

            publish_mjpeg_cap(cap)

        try:
            ok, frame_bgr = cap.read()
        except Exception as e:
            ok, frame_bgr = False, None
            try:
                state.set_last_error(f"MJPEG read failed (OpenCV): {e}")
            except Exception:
                pass

        if (not ok) or (frame_bgr is None):
            close_mjpeg_cap(cap)
            cap = None
            publish_mjpeg_cap(None)
            time.sleep(0.05)
            continue

        try:
            frame_rgb = state.cv2.cvtColor(frame_bgr, state.cv2.COLOR_BGR2RGB)
            hh, ww = frame_rgb.shape[:2]

            try:
                state.clear_last_error()
            except Exception:
                pass

            with state._video_lock:
                state._latest_frame_rgb_u8 = frame_rgb
                state._latest_frame_seq += 1
                state._frame_size = (int(ww), int(hh))

            with state._stats_lock:
                update_ingest_stats()

        except Exception as e:
            try:
                state.set_last_error(f"MJPEG decode failed: {e}")
            except Exception:
                pass
            close_mjpeg_cap(cap)
            cap = None
            publish_mjpeg_cap(None)
            time.sleep(0.05)

        time.sleep(0.0005)

    if cap is not None:
        close_mjpeg_cap(cap)
        publish_mjpeg_cap(None)
    shm_close()


def start_video_worker():
    if state._video_thread and state._video_thread.is_alive():
        return
    state._video_stop.clear()
    import threading
    state._video_thread = threading.Thread(target=video_worker, daemon=True)
    state._video_thread.start()


def stop_video_worker(clear_last=True):
    state._video_stop.set()

    with state._mjpeg_cap_lock:
        try:
            if state._mjpeg_cap is not None:
                state._mjpeg_cap.release()
        except Exception:
            pass
        state._mjpeg_cap = None

    if state._video_thread:
        try:
            state._video_thread.join(timeout=1.0)
        except Exception:
            pass
    state._video_thread = None

    shm_close()

    if clear_last:
        with state._video_lock:
            state._latest_frame_rgb_u8 = None
            state._latest_frame_seq += 1
            state._frame_size = (0, 0)


def video_off_hard():
    state.feed_running = False
    unregister_video_timer()
    stop_video_worker(clear_last=True)

    cam = get_active_camera()
    detach_bg_from_camera(cam)
    cleanup_all_cameras_m2b_slots()
    free_video_resources()


def video_on():
    state.feed_running = True
    state._uploaded_frame_seq = -1
    state._last_upload_ts = 0.0

    unregister_video_timer()

    cam = get_active_camera()
    cleanup_m2b_slots(cam)
    cleanup_all_cameras_m2b_slots()

    start_video_worker()
    bpy.app.timers.register(update_texture_timer, first_interval=0.0)


def restart_video_pipeline_if_needed():
    sc = bpy.context.scene
    if not sc.m2b_enable_feed:
        video_off_hard()
        return
    video_on()


def force_recreate_texture_next_upload():
    state._uploaded_frame_seq = -1
    state._float_buffer = None
    try:
        if state.webcam_texture is not None:
            bpy.data.images.remove(state.webcam_texture)
    except Exception:
        pass
    state.webcam_texture = None
    cam = get_active_camera()
    cleanup_m2b_slots(cam)
