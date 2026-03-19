# mp2b_mediapipe2blender/mp2b/addon.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy

from . import state
from . import props
from . import tracking
from . import video
from . import ui


class M2B_OT_ToggleAll(bpy.types.Operator):
    bl_idname = "m2b.toggle_all"
    bl_label = "Toggle MP2B"
    bl_options = {'REGISTER'}

    def execute(self, context):
        sc = context.scene

        # ---------------- STOP ----------------
        if sc.m2b_running:
            # stop video
            video.video_off_hard()

            # stop UDP thread
            if state.server_thread:
                state.server_thread.stop()
                try:
                    state.server_thread.join(0.6)
                except Exception:
                    pass
                state.server_thread = None

            # stop tracking timer
            try:
                if bpy.app.timers.is_registered(tracking.process_updates):
                    bpy.app.timers.unregister(tracking.process_updates)
            except Exception:
                pass

            try:
                sc.m2b_running = False
            except Exception:
                pass

            # immediate sync
            try:
                props._sync_cfg_from_scene()
            except Exception:
                pass

            # clear last error (best-effort)
            try:
                state.clear_last_error()
            except Exception:
                pass

            return {'FINISHED'}

        # ---------------- START ----------------
        # clear stale errors
        try:
            state.clear_last_error()
        except Exception:
            pass

        tracking.init_meshes()
        state.last_seq_map.update({'pose': -1, 'hands': -1, 'face': -1})
        state.last_seq_time.update({'pose': 0.0, 'hands': 0.0, 'face': 0.0})

        # Start UDP server
        state.server_thread = tracking.ServerThread(sc.m2b_host, sc.m2b_port)
        state.server_thread.start()

        # If bind failed, thread may terminate immediately -> surface fatal error via self.report()
        try:
            if not state.server_thread.is_alive():
                msg, _ts = ("", 0.0)
                try:
                    msg, _ts = state.get_last_error()
                except Exception:
                    msg = ""
                if not msg:
                    msg = f"UDP server failed to start on {sc.m2b_host}:{sc.m2b_port}"
                self.report({'ERROR'}, msg)

                # Ensure clean state
                try:
                    state.server_thread = None
                except Exception:
                    pass
                try:
                    sc.m2b_running = False
                except Exception:
                    pass
                try:
                    props._sync_cfg_from_scene()
                except Exception:
                    pass
                # no video should start if UDP failed
                try:
                    video.video_off_hard()
                except Exception:
                    pass

                return {'CANCELLED'}
        except Exception:
            # if we cannot verify thread state, continue (best-effort)
            pass

        # Start tracking timer
        try:
            if not bpy.app.timers.is_registered(tracking.process_updates):
                bpy.app.timers.register(tracking.process_updates, first_interval=0.0)
        except Exception:
            pass

        # Cleanup camera slots before starting video
        cam = video.get_active_camera()
        video.cleanup_m2b_slots(cam)
        video.cleanup_all_cameras_m2b_slots()

        # Mark running + sync cfg snapshot (CRITICAL for video worker)
        sc.m2b_running = True
        props._sync_cfg_from_scene()

        # Start/stop video depending on enable flag
        if sc.m2b_enable_feed:
            video.video_on()
        else:
            video.video_off_hard()

        return {'FINISHED'}


def register():
    bpy.utils.register_class(M2B_OT_ToggleAll)
    props.register_props()
    ui.register_ui()


def unregister():
    # clean shutdown
    try:
        sc = bpy.context.scene
        if sc and bool(getattr(sc, "m2b_running", False)):
            video.video_off_hard()

            if state.server_thread:
                state.server_thread.stop()
                try:
                    state.server_thread.join(0.6)
                except Exception:
                    pass
                state.server_thread = None

            try:
                if bpy.app.timers.is_registered(tracking.process_updates):
                    bpy.app.timers.unregister(tracking.process_updates)
            except Exception:
                pass

            try:
                sc.m2b_running = False
            except Exception:
                pass

        # clear last error (best-effort)
        try:
            state.clear_last_error()
        except Exception:
            pass

    except Exception:
        pass

    ui.unregister_ui()
    props.unregister_props()

    try:
        bpy.utils.unregister_class(M2B_OT_ToggleAll)
    except Exception:
        pass
