# mp2b_mediapipe2blender/mp2b/tracking.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
import threading
import socket
import time
import numpy as np
import struct
from . import state


def compose_rot_matrix(rx, ry, rz):
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    Ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float32)
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float32)
    return (Rz @ Ry @ Rx).astype(np.float32)


def avg_xy_distance_list(lst_a, lst_b):
    if not lst_a or not lst_b:
        return float("inf")
    n = min(len(lst_a), len(lst_b))
    if n == 0:
        return float("inf")
    a = np.asarray(lst_a[:n], dtype=np.float32)
    b = np.asarray(lst_b[:n], dtype=np.float32)
    return float(np.hypot(a[:, 0] - b[:, 0], a[:, 1] - b[:, 1]).mean())


def init_meshes():
    sc = bpy.context.scene
    with state.data_lock:
        state.raw_coords.clear()
        state.mesh_objects.clear()
        state.obj_objects.clear()
        state.visible = {"pose": True, "face": True, "left": False, "right": False}
        state._prev_coords = {"left": None, "right": None}

        for key, name, count, coll_name in state.SPECS:
            coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
            if coll_name not in sc.collection.children:
                sc.collection.children.link(coll)

            mesh = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
            obj = bpy.data.objects.get(name) or bpy.data.objects.new(name, mesh)
            if name not in coll.objects:
                coll.objects.link(obj)

            if len(mesh.vertices) != count:
                mesh.clear_geometry()
                mesh.from_pydata([(0, 0, 0)] * count, [], [])
                mesh.update()

            state.mesh_objects[key] = mesh
            state.obj_objects[key] = obj
            state.raw_coords[key] = [(0.0, 0.0, 0.0)] * count

            obj.hide_viewport = not state.visible[key]
            obj.hide_render = not state.visible[key]


def process_updates():
    if not state.server_thread or not getattr(state.server_thread, "running", False):
        return None

    tnow = time.time()
    for k in [k for k, v in list(state.reasm.items()) if (tnow - v["ts"] > state.REASM_TIMEOUT)]:
        state.reasm.pop(k, None)

    with state.data_lock:
        if not state.need_update:
            return 1.0 / 60.0

        keys_to_update = set(state.dirty_keys) if state.dirty_keys else set(state.raw_coords.keys())
        coords_snapshot = {k: list(state.raw_coords[k]) for k in keys_to_update if k in state.raw_coords}
        visible_snapshot = dict(state.visible)

        state.need_update = False
        state.dirty_keys.clear()

    sc = bpy.context.scene

    aspect = float(sc.m2b_aspect)
    sx, sy, sz = float(sc.m2b_axis_scale_x), float(sc.m2b_axis_scale_y), float(sc.m2b_axis_scale_z)
    px, py, pz = float(sc.m2b_pos_x), float(sc.m2b_pos_y), float(sc.m2b_pos_z)
    pd = float(sc.m2b_pose_depth_scale)
    face_h = float(sc.m2b_face_height)
    hands_h = float(sc.m2b_hands_height)

    R = compose_rot_matrix(float(sc.m2b_rot_x), float(sc.m2b_rot_y), float(sc.m2b_rot_z))

    # IMPORTANT:
    # We intentionally do NOT subtract a pose_root anymore.
    # Pose should follow the subject position in the video frame (like face/hands).

    for key in keys_to_update:
        obj = state.obj_objects.get(key)
        mesh = state.mesh_objects.get(key)
        if not obj or not mesh:
            continue

        vis = visible_snapshot.get(key, True)
        obj.hide_viewport = not vis
        obj.hide_render = not vis
        if not vis:
            continue

        src = coords_snapshot.get(key, [])
        count = state.KEY_COUNTS[key]
        if not src:
            continue

        pts = np.asarray(src[:count], dtype=np.float32)

        if key == "pose":
            arr = pts
            bx = (arr[:, 0] - 0.5) * aspect
            by = arr[:, 2] * pd
            bz = -(arr[:, 1] - 0.5)
            W = np.stack([bx, by, bz], axis=1).astype(np.float32)
            W[:, 0] = W[:, 0] * sx + px
            W[:, 1] = W[:, 1] * sy + py
            W[:, 2] = W[:, 2] * sz + pz
            RW = (W @ R.T).astype(np.float32)
            flat = RW.reshape(-1)

        elif key == "face":
            arr = pts
            bx = ((arr[:, 0] - 0.5) * aspect) * sx + px
            by = (arr[:, 2]) * sy + py
            bz = (-(arr[:, 1] - 0.5)) * sz + pz
            W = np.stack([bx, by, bz], axis=1).astype(np.float32)
            RW = (W @ R.T).astype(np.float32)
            RW[:, 2] += face_h
            flat = RW.reshape(-1)

        else:
            arr = pts
            bx = ((arr[:, 0] - 0.5) * aspect) * sx + px
            by = (arr[:, 2]) * sy + py
            bz = (-(arr[:, 1] - 0.5)) * sz + pz
            W = np.stack([bx, by, bz], axis=1).astype(np.float32)
            RW = (W @ R.T).astype(np.float32)
            RW[:, 2] += hands_h
            flat = RW.reshape(-1)

        mesh.vertices.foreach_set("co", flat.tolist())
        mesh.update()

    with state.data_lock:
        if visible_snapshot.get("left", False):
            state._prev_coords["left"] = coords_snapshot.get("left", None)
        if visible_snapshot.get("right", False):
            state._prev_coords["right"] = coords_snapshot.get("right", None)

    return 1.0 / 60.0


def accept_frame(model_id, seq, flags, payload):
    now = time.time()

    if model_id == state.MODEL_POSE:
        expected = state.KEY_COUNTS["pose"]
        arr = np.frombuffer(payload, dtype=np.float16).astype(np.float32)
        pts = arr[: expected * 3].reshape((-1, 3))
        with state.data_lock:
            state.raw_coords["pose"] = [(float(x), float(y), float(z)) for (x, y, z) in pts]
            state.visible["pose"] = True
            state.dirty_keys.add("pose")
            state.need_update = True
            state.last_seq_map["pose"] = seq
            state.last_seq_time["pose"] = now
        return

    if model_id == state.MODEL_FACE:
        expected = state.KEY_COUNTS["face"]
        arr = np.frombuffer(payload, dtype=np.float16).astype(np.float32)
        pts = arr[: expected * 3].reshape((-1, 3))
        with state.data_lock:
            state.raw_coords["face"] = [(float(x), float(y), float(z)) for (x, y, z) in pts]
            state.visible["face"] = True
            state.dirty_keys.add("face")
            state.need_update = True
            state.last_seq_map["face"] = seq
            state.last_seq_time["face"] = now
        return

    if model_id == state.MODEL_HANDS:
        if len(payload) < 2:
            return

        left_count = payload[0]
        right_count = payload[1]
        offs = 2

        def read_pts(count):
            nonlocal offs
            if count == 0:
                return []
            sz = count * 3 * 2
            buf = payload[offs : offs + sz]
            if len(buf) < sz:
                return []
            offs += sz
            arr = np.frombuffer(buf, dtype=np.float16).astype(np.float32)
            return [(float(arr[i]), float(arr[i + 1]), float(arr[i + 2])) for i in range(0, count * 3, 3)]

        left_pts = read_pts(left_count)
        right_pts = read_pts(right_count)

        with state.data_lock:
            if left_count == 0:
                state.visible["left"] = False
                state.dirty_keys.add("left")
            else:
                state.raw_coords["left"] = left_pts
                state.visible["left"] = True
                state.dirty_keys.add("left")

            if right_count == 0:
                state.visible["right"] = False
                state.dirty_keys.add("right")
            else:
                state.raw_coords["right"] = right_pts
                state.visible["right"] = True
                state.dirty_keys.add("right")

            if state.visible.get("left") and state.visible.get("right"):
                a = avg_xy_distance_list(state.raw_coords["left"], state.raw_coords["right"])
                if a <= state.HAND_OVERLAP_THRESHOLD:

                    def _dist_from_prev(side):
                        prev = state._prev_coords.get(side)
                        if not prev:
                            return float("inf")
                        n = min(len(prev), len(state.raw_coords[side]))
                        if n == 0:
                            return float("inf")
                        P = np.asarray(prev[:n], dtype=np.float32)
                        C = np.asarray(state.raw_coords[side][:n], dtype=np.float32)
                        return float(np.hypot(P[:, 0] - C[:, 0], P[:, 1] - C[:, 1]).mean())

                    dL = _dist_from_prev("left")
                    dR = _dist_from_prev("right")
                    keep = "left" if dL <= dR else "right"
                    drop = "right" if keep == "left" else "left"
                    state.visible[drop] = False
                    state.dirty_keys.add(drop)

            state.need_update = True
            state.last_seq_map["hands"] = seq
            state.last_seq_time["hands"] = now


def udp_listener(host, port, thr):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        sock.settimeout(0.2)
        # If we successfully bind, clear stale errors.
        try:
            state.clear_last_error()
        except Exception:
            pass
    except Exception as e:
        # NO print: store error for UI/operator to surface.
        try:
            state.set_last_error(f"UDP bind error on {host}:{port}: {e}")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass
        return

    while thr.running:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break

        if len(data) < state.HDR_SIZE:
            continue

        magic, ver, model, seq, flags, total_chunks, chunk_idx, payload_len, _pad = struct.unpack(
            state.HDR_FMT, data[: state.HDR_SIZE]
        )
        if magic != state.MAGIC or ver != state.VER:
            continue

        payload = data[state.HDR_SIZE :]
        if payload_len != len(payload):
            continue

        key_name = "pose" if model == state.MODEL_POSE else (
            "hands" if model == state.MODEL_HANDS else ("face" if model == state.MODEL_FACE else None)
        )
        if key_name is None:
            continue

        now = time.time()
        last_seq = state.last_seq_map.get(key_name, -1)
        last_time = state.last_seq_time.get(key_name, 0.0)

        if seq <= last_seq:
            if now - last_time > 0.6:
                state.last_seq_map[key_name] = -1
                state.last_seq_time[key_name] = 0.0
                for rkey in [rk for rk in list(state.reasm.keys()) if rk[0] == model]:
                    state.reasm.pop(rkey, None)
            else:
                continue

        if model in (state.MODEL_POSE, state.MODEL_HANDS) and total_chunks <= 1:
            accept_frame(model, seq, flags, payload)
            continue

        if model == state.MODEL_FACE:
            if total_chunks <= 1:
                accept_frame(model, seq, flags, payload)
                continue

            rkey = (model, seq)
            entry = state.reasm.get(rkey)
            if entry is None:
                entry = {"total": total_chunks, "chunks": {}, "ts": time.time(), "flags": flags}
                state.reasm[rkey] = entry

            entry["chunks"][chunk_idx] = payload
            entry["ts"] = time.time()

            tnow = time.time()
            for k in [k for k, v in list(state.reasm.items()) if (tnow - v["ts"] > state.REASM_TIMEOUT)]:
                state.reasm.pop(k, None)

            if len(entry["chunks"]) == entry["total"]:
                buf = b"".join(entry["chunks"][i] for i in range(entry["total"]))
                state.reasm.pop(rkey, None)
                accept_frame(model, seq, entry["flags"], buf)

    try:
        sock.close()
    except Exception:
        pass


class ServerThread(threading.Thread):
    def __init__(self, h, p):
        super().__init__(daemon=True)
        self.host, self.port = h, p
        self.running = True

    def run(self):
        udp_listener(self.host, self.port, self)

    def stop(self):
        self.running = False
