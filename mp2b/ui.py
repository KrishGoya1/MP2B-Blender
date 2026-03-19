# mp2b_mediapipe2blender/mp2b/ui.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
import time
from . import state


class M2B_PT_Main(bpy.types.Panel):
    bl_label = "MP2B 0.1 BETA"
    bl_idname = "M2B_PT_Main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MP2B'

    def draw(self, ctx):
        l, sc = self.layout, ctx.scene

        # ---- last error (NO print) ----
        try:
            msg, ts = state.get_last_error()
        except Exception:
            msg, ts = "", 0.0

        if msg:
            age = 0.0
            try:
                age = max(0.0, time.time() - float(ts))
            except Exception:
                age = 0.0

            ebox = l.box()
            ebox.label(text="MP2B Error", icon='ERROR')
            # Mostra messaggio (una riga). Se lungo, Blender lo tronca visivamente.
            ebox.label(text=str(msg))

            # Se l'errore è “vecchio”, lo indichiamo (senza essere invasivi)
            if age >= 10.0:
                ebox.label(text=f"(last error {age:.0f}s ago)")

        box = l.box()
        box.label(text="Tracking (UDP)")
        row = box.row(align=True)
        row.prop(sc, "m2b_host", text="Host")
        row.prop(sc, "m2b_port", text="Port")

        box.separator()
        box.label(text="Transform Mapping")

        r = box.row(align=True)
        r.column(align=True).prop(sc, "m2b_pos_x", text="Pos X")
        r.column(align=True).prop(sc, "m2b_pos_y", text="Pos Y")
        r.column(align=True).prop(sc, "m2b_pos_z", text="Pos Z")

        r = box.row(align=True)
        r.column(align=True).prop(sc, "m2b_rot_x", text="Rot X")
        r.column(align=True).prop(sc, "m2b_rot_y", text="Rot Y")
        r.column(align=True).prop(sc, "m2b_rot_z", text="Rot Z")

        r = box.row(align=True)
        r.column(align=True).prop(sc, "m2b_axis_scale_x", text="Scale X")
        r.column(align=True).prop(sc, "m2b_axis_scale_y", text="Scale Y")
        r.column(align=True).prop(sc, "m2b_axis_scale_z", text="Scale Z")

        r = box.row(align=True)
        r.prop(sc, "m2b_aspect", text="Aspect")
        r.prop(sc, "m2b_pose_depth_scale", text="Pose Depth")

        r = box.row(align=True)
        r.prop(sc, "m2b_face_height", text="Face Height")
        r.prop(sc, "m2b_hands_height", text="Hands Height")

        box2 = l.box()
        box2.prop(sc, "m2b_enable_feed", text="Enable Camera Feed")

        col = box2.column()
        col.enabled = sc.m2b_enable_feed

        col.prop(sc, "m2b_video_source", text="Source")
        col.prop(sc, "m2b_video_scale", text="Output Scale")
        col.prop(sc, "m2b_video_fps_cap", text="Blender Upload FPS")

        col.separator()
        col.prop(sc, "m2b_ingest_mode", text="Ingest Mode")
        if sc.m2b_ingest_mode == "FIXED":
            col.prop(sc, "m2b_ingest_fps_cap", text="Ingest FPS")

        if sc.m2b_video_source == "SHM":
            col.prop(sc, "m2b_shm_name", text="SHM Name")
        else:
            col.prop(sc, "m2b_mjpeg_url", text="URL")
            if state.cv2 is None:
                col.label(text="OpenCV not available: MJPEG will NOT work", icon='ERROR')

        box3 = l.box()
        box3.label(text="Armature Retargeting")
        box3.prop(sc, "m2b_target_armature")
        if sc.m2b_target_armature:
            box3.operator("m2b.setup_rigging", text="Setup MP2B Rigging for Armature")

        # stats (best-effort)
        try:
            with state._stats_lock:
                ing = float(state._stat_ingest_fps)
                upl = float(state._stat_upload_fps)
                dups = int(state._stat_bg_dup_cleaned)
        except Exception:
            ing, upl, dups = 0.0, 0.0, 0

        sbox = box2.box()
        srow = sbox.row(align=True)
        srow.label(text=f"Ingest ~ {ing:.1f} fps")
        srow.label(text=f"Upload ~ {upl:.1f} fps")
        if dups > 0:
            sbox.label(text=f"BG dup removed: {dups}", icon='INFO')

        l.operator("m2b.toggle_all", text=("STOP" if sc.m2b_running else "START"), depress=sc.m2b_running)


def register_ui():
    bpy.utils.register_class(M2B_PT_Main)


def unregister_ui():
    try:
        bpy.utils.unregister_class(M2B_PT_Main)
    except Exception:
        pass
