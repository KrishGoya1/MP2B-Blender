# mp2b_mediapipe2blender/mp2b/addon.py
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy

from . import state
from . import props
from . import tracking
from . import video
from . import ui


class M2B_OT_SetupRigging(bpy.types.Operator):
    bl_idname = "m2b.setup_rigging"
    bl_label = "Setup MP2B Rigging"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sc = context.scene
        arm = sc.m2b_target_armature
        if not arm or arm.type != 'ARMATURE':
            self.report({'ERROR'}, "Select a valid Target Armature first.")
            return {'CANCELLED'}

        pose_mesh = bpy.data.objects.get("PoseMesh")
        if not pose_mesh:
            self.report({'ERROR'}, "PoseMesh not found. Please click START first to generate tracking meshes.")
            return {'CANCELLED'}

        if bpy.context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        vgs = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
        for v in vgs:
            vg_name = f"VG_{v}"
            vg = pose_mesh.vertex_groups.get(vg_name)
            if not vg:
                vg = pose_mesh.vertex_groups.new(name=vg_name)
            vg.add([v], 1.0, 'REPLACE')

        bone_map = {
            "mixamorig:Hips": [("COPY_LOCATION", "VG_23", None, 0, 0.5), ("COPY_LOCATION", "VG_24", None, 0, 0.5)],
            "mixamorig:Head": [("DAMPED_TRACK", "VG_0", None, 0, 1.0)],
            "mixamorig:LeftForeArm": [("IK", "VG_15", "VG_13", 2, 1.0)],
            "mixamorig:RightForeArm": [("IK", "VG_16", "VG_14", 2, 1.0)],
            "mixamorig:LeftLeg": [("IK", "VG_27", "VG_25", 2, 1.0)],
            "mixamorig:RightLeg": [("IK", "VG_28", "VG_26", 2, 1.0)]
        }

        for bone_name, constraints_data in bone_map.items():
            bone = arm.pose.bones.get(bone_name)
            if not bone:
                bone = arm.pose.bones.get(bone_name.replace("mixamorig:", ""))
            if not bone:
                continue
            
            for c in list(bone.constraints):
                if c.name.startswith("M2B_"):
                    bone.constraints.remove(c)

            for i, (ctype, subt, polesubt, chain, infl) in enumerate(constraints_data):
                c = bone.constraints.new(ctype)
                c.name = f"M2B_{ctype}_{i}"
                c.target = pose_mesh
                c.subtarget = subt
                c.influence = infl
                if ctype == "IK":
                    c.chain_count = chain
                    if polesubt:
                        c.pole_target = pose_mesh
                        c.pole_subtarget = polesubt
                elif ctype == "DAMPED_TRACK":
                    c.track_axis = 'TRACK_Z'

        self.report({'INFO'}, "MP2B Rigging Setup Complete (Direct to PoseMesh).")
        return {'FINISHED'}


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

        import os
        dummy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Dummy.fbx")
        fallback_path = r"c:\Users\Krish\Downloads\MP2B 01 BETA\MP2B 01 BETA\MP2B_Extension\mp2b_extension\mp2b_extension\Dummy.fbx"
        if not os.path.exists(dummy_path) and os.path.exists(fallback_path):
            dummy_path = fallback_path
        
        dummy_arm = sc.m2b_target_armature
        if not dummy_arm or dummy_arm.name not in bpy.data.objects:
            for obj in bpy.data.objects:
                if obj.type == 'ARMATURE' and 'Dummy' in obj.name:
                    dummy_arm = obj
                    break
        
        if not dummy_arm and os.path.exists(dummy_path):
            try:
                # Deselect all first
                if bpy.context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.select_all(action='DESELECT')
                
                bpy.ops.import_scene.fbx(filepath=dummy_path, use_anim=False)
                
                is_tiny = False
                for obj in context.selected_objects:
                    if obj.type == 'ARMATURE':
                        dummy_arm = obj
                        if obj.scale[0] < 0.1:
                            is_tiny = True

                    if obj.animation_data:
                        obj.animation_data_clear()

                if is_tiny:
                    for obj in context.selected_objects:
                        obj.scale = (obj.scale[0] * 100.0, obj.scale[1] * 100.0, obj.scale[2] * 100.0)
                    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                    
            except Exception as e:
                print("Failed to auto-import Dummy.fbx:", e)

        if dummy_arm:
            sc.m2b_target_armature = dummy_arm
            try:
                bpy.ops.m2b.setup_rigging()
            except Exception:
                pass

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
    bpy.utils.register_class(M2B_OT_SetupRigging)
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
        bpy.utils.unregister_class(M2B_OT_SetupRigging)
    except Exception:
        pass
