# mp2b_mediapipe2blender/__init__.py
# MediaPipe 2 Blender (MP2B)
# Author: Tommaso Malaisi
# License: GPL-3.0-or-later

bl_info = {
    "name": "MediaPipe 2 Blender (MP2B)",
    "author": "Tommaso Malaisi",
    "version": (0, 0, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > M2B",
    "description": "MediaPipe tracking via UDP + camera feed (SHM/MJPEG)",
    "category": "Animation",
}

_addon = None


def _get_addon():
    global _addon
    if _addon is None:
        from .mp2b import addon as _a
        _addon = _a
    return _addon


def register():
    _get_addon().register()


def unregister():
    try:
        _get_addon().unregister()
    except Exception:
        pass
